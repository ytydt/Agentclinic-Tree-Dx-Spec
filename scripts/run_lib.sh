#!/usr/bin/env bash
# §30 HYBRID slot scheduler: 1 rep/GPU + N reps/CPU, per-CASE resume, single-
# process retry, CPU pinning for repeatedly-crashing reps. Source this from a
# driver, then call `run_reps "tag|flags" ...`.
#
# Design (addresses the fork segfault RCA + user's scheduling spec):
#   (1) SLOTS — a fixed pool of execution slots runs reps concurrently:
#         GPU slots: one per device in GPU_POOL (1 rep/GPU — avoids the
#           cross-process cuda:N contention that caused ~1/3 crashes).
#         CPU slots: CPU_SLOTS reps pinned to TREE_DX_EMBED_DEVICE=cpu (the box
#           has ample RAM; OMP/MKL are capped to 2 in the eval so co-located CPU
#           reps don't oversubscribe cores → no OpenMP thread-explosion segfault).
#       This keeps every processor busy without crashing and minimises wall time.
#   (2) PER-CASE RESUME — every (re)launch passes `--resume`, so a re-run carries
#       over already-scored (OK/XX) cases from the tag's newest JSON and only
#       recomputes unscored/contaminated (PROTO/ERR/TIMEOUT/NOANS/missing) cases.
#       Correct outputs are NEVER wasted on a whole-9 rerun.
#   (3) SINGLE-PROCESS RETRY + CPU PIN — a rep whose JSON is still incomplete
#       after its process exits (segfault/abort) is requeued. After GPU_TRIES GPU
#       crashes it is pinned to a CPU slot (FAISS-search-lock + OMP cap make CPU
#       crash-free). Capped at MAX_ATTEMPTS; partial (scored≥1) is then accepted.
#   (4) CONTAMINATION-AWARE COMPLETION — a rep is DONE only when ALL cases are
#       scored (OK/XX). scored==0 (billing/PROTO outage) or partial triggers a
#       resume re-run; only the contaminated cases are redone (or all 9 if the
#       whole repeat was starved by a billing outage).
#
# Idempotent: a fully-scored repeat is skipped, so re-invoking only fills gaps.

: "${CASES:=1,9,13,14,17,18,22,23,24}"
: "${NCASES:=9}"            # cases per repeat (for the all-scored completion test)
: "${WORKERS:=9}"
: "${TEMP:=0}"
: "${CASE_TIMEOUT:=25640}"
: "${GPU_POOL:=0 1 2}"      # one rep per GPU
: "${CPU_SLOTS:=2}"         # 2–3 reps on CPU concurrently
: "${GPU_TRIES:=2}"         # GPU crashes before pinning a rep to CPU
: "${MAX_ATTEMPTS:=4}"      # total (re)launches per rep before accepting partial
: "${EXTRA_FLAGS:=}"        # appended to every rep (e.g. --no-secondary-cache)
read -r -a _GPUS <<< "$GPU_POOL"

# _scored <tag> → prints "scored total" of the newest JSON (0 0 if none).
_scored() {
  local tag="$1" js
  js=$(ls -1t logs/medbullets_conc_"${tag}"_*.json 2>/dev/null | head -1)
  [ -z "$js" ] && { echo "0 0"; return; }
  python3 - "$js" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("0 0"); sys.exit()
scored = sum(1 for r in d if r.get("status") in ("OK", "XX"))
print(f"{scored} {len(d)}")
PY
}

# _rep_done <tag> → 0 if ALL cases scored (OK/XX), else 1.
_rep_done() {
  local s t; read -r s t < <(_scored "$1")
  [ "$t" -ge "$NCASES" ] && [ "$s" -ge "$t" ] && [ "$s" -ge "$NCASES" ]
}

# _launch <device> <tag> <flags...> — async; returns pid via _LAST_PID.
_launch() {
  local device="$1" tag="$2"; shift 2
  local flags="$*"
  # §30 per-experiment isolation: namespace the tier-2 cache by ARM (= tag with
  # trailing _<rep> stripped) so arms are independent and only reps of the same
  # arm share. Skipped when the cache is disabled (--no-secondary-cache).
  local ns_arg=""
  if [[ "$EXTRA_FLAGS $flags" != *"--no-secondary-cache"* ]]; then
    local arm="${tag%_*}"   # nc_bk_off_1 → nc_bk_off
    ns_arg="--cache-namespace ${arm}"
  fi
  echo "[$(date +%H:%M:%S)]   launch ${tag} on ${device}  flags='${flags} ${EXTRA_FLAGS} ${ns_arg}'" >> "logs/run_${tag}.out"
  TREE_DX_EMBED_DEVICE="${device}" \
    conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
      --temp "$TEMP" --resume $flags $EXTRA_FLAGS $ns_arg --tag "${tag}" >> "logs/run_${tag}.out" 2>&1 &
  _LAST_PID=$!
}

# run_reps "tag1|flags1" "tag2|flags2" ...
run_reps() {
  local jobs=("$@")
  # Build slot device list: GPU devices (cuda:N) then CPU slots.
  local slots=() s
  for g in "${_GPUS[@]}"; do slots+=("cuda:${g}"); done
  for ((s=0; s<CPU_SLOTS; s++)); do slots+=("cpu"); done
  local nslots=${#slots[@]}
  echo "[$(date +%H:%M:%S)] hybrid scheduler: ${#_GPUS[@]} GPU + ${CPU_SLOTS} CPU = ${nslots} slots; ${#jobs[@]} reps"

  # per-job state
  declare -A ATT GPUFAIL CPUONLY DONE
  local queue=()
  for job in "${jobs[@]}"; do
    local tag="${job%%|*}"
    : > "logs/run_${tag}.out"
    if _rep_done "$tag"; then
      echo "[$(date +%H:%M:%S)] SKIP ${tag} (already 9/9 scored)"; DONE[$tag]=1
    else
      queue+=("$job"); ATT[$tag]=0; GPUFAIL[$tag]=0; CPUONLY[$tag]=0
    fi
  done

  # slot occupancy
  local -a slot_pid slot_job
  for ((s=0; s<nslots; s++)); do slot_pid[$s]=0; slot_job[$s]=""; done

  while :; do
    # reap finished slots
    for ((s=0; s<nslots; s++)); do
      local pid=${slot_pid[$s]}
      if [ "$pid" != "0" ] && ! kill -0 "$pid" 2>/dev/null; then
        local job="${slot_job[$s]}"; local tag="${job%%|*}"
        slot_pid[$s]=0; slot_job[$s]=""
        if _rep_done "$tag"; then
          local sc; read -r sc _ < <(_scored "$tag")
          echo "[$(date +%H:%M:%S)] DONE ${tag} (${sc}/${NCASES})"; DONE[$tag]=1
        else
          local sc tt; read -r sc tt < <(_scored "$tag")
          # crash if the device was a GPU and JSON gained no full coverage
          if [[ "${slots[$s]}" == cuda:* ]] && [ "$sc" -lt "$NCASES" ]; then
            GPUFAIL[$tag]=$(( ${GPUFAIL[$tag]} + 1 ))
            [ "${GPUFAIL[$tag]}" -ge "$GPU_TRIES" ] && CPUONLY[$tag]=1
          fi
          if [ "${ATT[$tag]}" -ge "$MAX_ATTEMPTS" ]; then
            if [ "$sc" -ge 1 ]; then
              echo "[$(date +%H:%M:%S)] ACCEPT PARTIAL ${tag} (${sc}/${NCASES}) after ${ATT[$tag]} attempts"
            else
              echo "[$(date +%H:%M:%S)] PERSISTENT FAIL ${tag} (0 scored) after ${ATT[$tag]} attempts"
            fi
            DONE[$tag]=1
          else
            echo "[$(date +%H:%M:%S)] REQUEUE ${tag} (scored ${sc}/${tt}, gpuFail=${GPUFAIL[$tag]}, cpuOnly=${CPUONLY[$tag]})"
            queue+=("$job")
          fi
        fi
      fi
    done

    # fill free slots
    for ((s=0; s<nslots; s++)); do
      [ "${slot_pid[$s]}" != "0" ] && continue
      [ "${#queue[@]}" -eq 0 ] && continue
      local dev="${slots[$s]}"
      # pick a job for this slot: CPU slots take any; GPU slots skip cpu-only jobs
      local pick=-1 qi
      for qi in "${!queue[@]}"; do
        local jtag="${queue[$qi]%%|*}"
        if [[ "$dev" == cuda:* ]] && [ "${CPUONLY[$jtag]}" = "1" ]; then continue; fi
        pick=$qi; break
      done
      [ "$pick" -lt 0 ] && continue
      local job="${queue[$pick]}"
      # remove picked from queue
      queue=("${queue[@]:0:$pick}" "${queue[@]:$((pick+1))}")
      local tag="${job%%|*}"; local flags="${job#*|}"
      ATT[$tag]=$(( ${ATT[$tag]} + 1 ))
      echo "[$(date +%H:%M:%S)] DISPATCH ${tag} → slot${s}(${dev}) attempt ${ATT[$tag]}/${MAX_ATTEMPTS}"
      _launch "$dev" "$tag" "$flags"
      slot_pid[$s]=$_LAST_PID; slot_job[$s]="$job"
      sleep 2
    done

    # termination: queue empty and all slots idle
    local busy=0
    for ((s=0; s<nslots; s++)); do [ "${slot_pid[$s]}" != "0" ] && busy=1; done
    if [ "${#queue[@]}" -eq 0 ] && [ "$busy" -eq 0 ]; then break; fi
    sleep 10
  done

  echo "[$(date +%H:%M:%S)] ===== run_reps complete ====="
  for job in "${jobs[@]}"; do
    local tag="${job%%|*}"; local sc tt; read -r sc tt < <(_scored "$tag")
    echo "  ${tag}: ${sc}/${tt} scored"
  done
}
