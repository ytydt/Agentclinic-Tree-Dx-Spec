# E8：非时间化硬否证与时间/范围感知软否证的病例轨迹解剖

## 判定

E8 明确推翻了“一个显式阴性只要与候选的典型表现冲突，就可安全地作不分时间、对象、解剖和检查灵敏度的绝对 veto”。在 hard 与 soft 都成功的 183 例中，hard 对暴露的 gold 作了 8 次硬否证，soft 为 0（精确配对 `p=0.0078`）；加上 soft schema 失败的一例，hard 共否证 9 个 gold。根代理逐例审查全部 9 例：8 例是临床 overreach，1 例由构造器把阳性 CT 反写成“无异常”后制造，0 例能支持该绝对否证。

但 E8 没有证明“换成 soft prompt 就会稳定提高最终准确率”。共同成功的 183 例中，soft 相对 hard 仅净增 3 个正确病例（18→21；hard-only 2，soft-only 5；`+1.64 pp`，病例 bootstrap 95% CI `[-1.09,+4.37] pp`，McNemar `p=0.453`）。只看 gold 已在固定池暴露的 33 例是 18→21（`+9.09 pp`，95% CI `[-6.06,+24.24] pp`），仍远不足以声称净收益。

更深的结果是：时间字段确实能改变模型落点，却没有显示净判别方向；而无临床意义的 ledger 行顺序产生了同量级的不稳定。非法错配 time/episode 后，125 例有 29 次 champion flip（23.2%），正确数 15→15；只打乱合法行序时，191 例有 47 次 flip（24.6%），正确数 22→21。因此，不能把 hard↔soft 的 91/183 次 champion flip 全解释为时间理解。当前 selector 同时存在时间字段响应、序位敏感和广泛的错候选间漂移。

最可靠的结论分为两层：**绝对否证不安全，必须保留 time/scope/sensitivity 并允许撤销；当前 soft-veto ranker 的净准确率增益尚未识别。**

## 设计：只改变否证合同

样本从 E4 的 400 个固定 canonical pool 中按输入标记预先选择 220 例，DA/MCR 各 110；入选条件为 clean vignette 至少一个时间标记和三个否定/正常标记。候选 ID、标签、顺序和 clean vignette 在所有主臂冻结，不使用 gold、选项、历史 champion、来源名、旧 rank 或 score。

候选盲 Gemini 构造器先提取 2–6 个带原文 quote 的 negative events：observation、negation kind、time anchor、episode、person scope、anatomy、test context 和 sensitivity。为使时间置换可识别，每个被提取阴性的原文 span 从 selector 上下文中精确替换为 ledger 引用；否则模型可从未改动原文直接纠正伪时间。selector 只看到同一正向上下文、同一候选池和 ledger，不看到 negative source quote。

四个 selector 臂为：

1. `atemporal_hard_veto`：故意忽略时间、episode、scope、解剖、灵敏度和后续演变，把冲突阴性作绝对 veto；
2. `time_scope_soft_veto`：只有同一对象、解剖、episode 且检查在该时点足够敏感时才允许 hard veto；否则为 soft uncertainty；
3. `time_scope_soft_legal_order`：与 2 内容完全相同，只确定性改变 ledger 行序；
4. `time_scope_soft_invalid_time`：保持 observation、scope、anatomy、test context、候选和上下文不变，仅循环错配 time anchor 与 episode。只有具备至少两个不同锚的 125 例进入该干预。

离线完整性检查证明：193 个构造成功病例的 hard/soft API payload 字节内容相同，唯一变化是 prompt；legal-order 的 ledger 内容逐事件完全相同；125 个 invalid-time 病例的所有非时间字段完全相同。598 个被干预 event 中，327 个实际改变了 time 或 episode；同值重复锚未被伪报为改变。

## 病例流与候选暴露上限

构造器在 transport 层 220/220 返回，但只有 193/220 通过科学合同。27 例 fail-closed：17 个重叠原文 span、6 个 quote 不落原文、3 个 event 数量错误、1 个 sensitivity 非法。任何失败都保留在 220 例 ITA 表中。

固定 pool 只有 39/220（17.7%）按 exact/frozen-synonym 暴露 gold；其中 35 例构造成功，hard/soft 又只有 33 例共同成功。因而全样本约 10% 的 top-1 不是一个可解释的端到端性能数字，主要被候选暴露上限截断。主报告同时给出：

- 全 ITA/共同成功结果，刻画运行与系统行为；
- gold-exposed 共同成功结果，条件性刻画 selector 转化；
- 不把 gold-exposed 条件结果外推成 generator 或端到端准确率。

## 配对结果

| 比较（右−左） | 共同成功 n | champion flip | 正确数左→右 | 独赢左/右 | 净差 | bootstrap 95% CI | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|
| hard → soft，全部 | 183 | 91 (49.7%) | 18→21 | 2 / 5 | +1.64 pp | −1.09, +4.37 | 0.453 |
| hard → soft，gold exposed | 33 | 13 (39.4%) | 18→21 | 2 / 5 | +9.09 pp | −6.06, +24.24 | 0.453 |
| soft → legal order，全部 | 191 | 47 (24.6%) | 22→21 | 3 / 2 | −0.52 pp | −3.14, +1.57 | 1.000 |
| soft → legal order，gold exposed | 34 | 7 (20.6%) | 22→21 | 3 / 2 | −2.94 pp | −14.71, +8.82 | 1.000 |
| soft → invalid time，全部 | 125 | 29 (23.2%) | 15→15 | 1 / 1 | 0 | −2.40, +2.40 | 1.000 |
| soft → invalid time，gold exposed | 25 | 2 (8.0%) | 15→15 | 1 / 1 | 0 | −12.0, +12.0 | 1.000 |

soft 不是“从不硬否证”：主 soft 臂 192 个成功病例中 36 例仍使用至少一次 hard veto，共 71 次；只是没有否证 gold。hard 臂在 184 个成功病例中有 155 例使用 hard veto，共 539 次。处理确实大幅改变 veto policy，但其准确率转化弱得多。

## 九个 gold hard-veto 的机制

### 被 soft 救回 top-1 的四例

- `DA_d2_seq100/87`：无心包摩擦音被 hard 当成排除 myopericarditis；soft 正确保留，而正常冠脉仍可排除阻塞性 MI/ACS。
- `MCR_seq200b/336`：无发热、乏力等全身症状被用来排除 subacute thyroiditis；这些不是必备表现，soft 选回 gold。
- `MCR_seq200b/345`：normal urine calcium/no stones 被当成对 HHRH 的绝对排除；FGF23-independent 生化谱和 nephrocalcinosis 仍支持 gold，soft 选回，但合法行序又把收益翻掉，说明 rescue 不稳定。
- `MCR_v2_seq100/174`：抗壁细胞/内因子抗体阴性和近正常内镜被 hard 用来排除 autoimmune gastritis；活检的壁细胞层退变、H+/K+-ATPase 降低和 ECL hyperplasia 更直接，soft 正确保留。

### 撤销错误 veto 但未救回的四例

- `DA_d2_heldout200b/486`：无周围神经增粗/无汗不能排除 histoid leprosy；soft 只到 lepromatous leprosy，legal-order 才偶然选中 histoid，显示本体具体度与序位仍是瓶颈。
- `MCR_seq200b/480`：初期无复视、吞咽困难或肢体无力不能绝对排除 bulbar myasthenia gravis；soft 撤销 veto 后仍锚定 TIA，而且六事件预算漏掉了阴性 fatigue/neostigmine 两个决定性反证。
- `MCR_v1_seq100/28`：当前 afebrile 不能抹去既往一月发热，也不能排除 TEN；soft 仍选 DRESS。病例本身 eosinophilia/肝损与黏膜大疱并存，可辨识性仅部分。
- `MCR_v2_seq100/173`：不是 veto policy 本身的问题。构造器把明确显示 15 mm 硬膜下积液和 13 mm 中线移位的 CT quote 写成“无其他异常”，再据此 hard-veto chronic subdural hematoma。这是关系/极性反转导致的伪否证。

第九例 `DA_d2_heldout100/349` 的 soft 输出因非法 event ID fail-closed：无发热、无内脏受累不能绝对排除局限性 cutaneous histoplasmosis；hard 的 veto 仍是 overreach，但无法观察 soft 是否 rescue，故不进入配对收益。

这九例说明“否证错误减少”与“最终答案增加”是两个不同终点。soft 在 8 个可配对 veto 中去掉全部 8 个，且 4 个转成正确；另外 4 个被候选具体度、早期锚定或其他证据权重继续阻断。

## 时间字段为什么有行为效应，却没有净收益

非法时间臂并非无效处理。根代理审查的 23 个可干预样本都确认 ledger-B 的时间/episode 置换改变了临床含义；例如把“术后两个月检查”移到“术前感染”，或把初次就诊的正常神经查体移到严重发作的上门检查。全 125 例也有 29 次 champion flip。

然而三点阻止把它写成时间判别增益：

1. 正确性方向完全对称（1 rescue、1 harm）；
2. gold-exposed 25 例只有 2 次 champion flip，说明多数时间反应发生在 gold 不可达的错候选之间；
3. 只改变合法行序就有更高的 24.6% flip，准确性同样近零净变。温度 0、多 provider 和长 reasoning 并没有提供病例级确定性。

两个方向相反的病例最有说明力。`MCR_seq200b/336` 的正确 soft 结果在错时后退回 vaccine-thyroiditis；这符合时间字段被使用。`MCR_seq200b/470` 则是 hard 正确、soft 错成 Stargardt，而 legal-order 与 invalid-time 都回到 cone-rod dystrophy；这里“错误时间反而修复答案”只能由排序吸引域/序位敏感解释，不能称为正确时间机制。

因此，下一版不能把 time 字段仅作为 prompt 中的一列。需要确定性的时间约束检查和对照排序：同一事件的时间变化若没有改变其候选对的 decisive contrast，就不应让全局 champion 任意跳转。

## 构造器仍是因果链中的主动风险

30 个根代理病例是机制富集样本，不用于估计总体错误率。其中 ledger-A 为 faithful 23、minor 1、major 6。主要错误不是措辞：

- 把未做代谢评估写成患者“阴性”；
- 把父亲的眼压归到 proband 的 patient scope；
- 把孕妇的病史、用药与创伤史归到 fetal/patient，而非 maternal scope；
- 从无参考范围的裸数值推断“正常”；
- 六事件上限保留泛化 normal labs，却漏掉对当前鉴别最关键的阴性检查；
- 最严重者直接反转阳性 CT。

构造期还发现 680 个 `adequate sensitivity` 没有 vignette basis。依据调用前 prompt 的硬合同，这些值从原始响应确定性降级为 `unknown`，而不是由人工补成某个临床灵敏度。若不做这一步，soft 臂也会在大量并无证据的“充分敏感检查”上重新制造 hard veto。

这与 E6 的图关系错误形成同一机制：结构字段不是免费的格式，它们是新增命题。RCR-3 必须让极性、对象、time 和 scope 都绑定原文 span；无法验证的 sensitivity 只能是 unknown，缺失检查不能编码成 negative。

## 异质 LLM 审计的可靠性边界

OpenAI GPT-4.1 mini 作为与 Gemini builder、DeepSeek selector 均不同的第二读者，成功 25/29；4 例 schema fail-closed。它有效指出了若干真实问题，包括慢性硬膜下血肿 CT 反转、父/女儿时间混排和若干过度 hard veto。

但它系统性混淆了两层：把实验故意制造的 ledger-B 错时算成原始 ledger-A builder 错误；又在“reference hard-veto validity”字段中审查其他非 reference 候选。根代理在 29 个代理样本中全部至少改了一个字段，共 63 个字段分歧；另补审 soft schema 失败的第九个 hard-veto，最终人工覆盖 30 例。

因此代理输出完整保留用于追责，但报告只使用 `manual_audit.jsonl` 的最终分层。不同模型族降低了同族偏差，却没有消除任务定义偏差。

## 运行可用性与环境适配

E8 连同异质审计共记录 946 个 semantic calls、1082 个 physical attempts、122 万 input tokens、267 万 output tokens；latency 求和约 62,489 秒（并发下不能当墙钟时间）。DeepSeek 四臂经多个 OpenRouter provider 路由，无 Groq；Gemini builder 走 Google，代理审计走 OpenAI。

尽管请求已设置 `reasoning.max_tokens=64` 和 `exclude=true`，hard 臂仍产生 921,083 output tokens、254 physical attempts，并多次出现 `finish_reason=length` 与 180 秒 timeout。该异常解释 hard 的较低服务率，但不解释临床方向；所有技术失败均保留。

环境没有 `openai`、`httpx` 或 `requests` 包，所以生产 `RobustLLMClient` 自动使用 dependency-free OpenRouter transport。代码仍保留并测试官方 OpenAI SDK 分支，依赖存在且环境选择时会优先使用；E8 没有写一个替代生产合同的实验专用 HTTP terminal。API key 可用，未写入文件或日志。

## 对 RCR-3 的直接约束

1. 禁止 atemporal absolute veto；negative 默认 soft，只有可验证的同对象、同解剖、同 episode、同时间且充分敏感检查才允许 hard。
2. 所有 veto 可撤销并保留触发 event/span；低先验但有高特异阳性证据的候选不能被单个典型表现缺失淘汰。
3. `not tested`、`no evaluation` 与 `tested negative` 是不同类型；family、maternal、fetal、proband 必须不同 scope。
4. comparator 应在候选对共享的 decisive facts 上排序，不能把 ledger 行序当票数或优先级。
5. time/episode 先做确定性一致性校验，再交给 LLM；字段置换不应在没有对应 contrast 变化时重写全局 champion。
6. soft veto 只能解决错误排除，不能修复 gold 未暴露、复合对象缺失或 subtype identity。候选层与否证层必须分开评估。
7. 完整性 gate 应在 polarity 反转、scope collision、关键阴性遗漏或低 margin/cycle 时回看原文，而不是无条件增加一次调用。

E8 是开发集机制实验，不是确认性优越性试验。它足以禁止一种危险操作，却不足以冻结 soft ranker 为新最佳算法。
