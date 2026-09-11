# 独立指南执行研究

本分支从`cursor4@cee67799d465b4284b98268be726e8842c7c7627`建立，用于研究符号化/程序化临床指南的文献脉络、缺陷与复现条件。

独立子仓库为[ytydt/Executable-Clinical-Guidelines](https://github.com/ytydt/Executable-Clinical-Guidelines)，默认私有，以Git子模块固定在本目录下的`executable-clinical-guidelines`。该研究独立于父仓生产诊断算法；MCR/DA仅作为候选病例来源之一。

- [主报告](executable-clinical-guidelines/REPORT.md)
- [代码、数据与知识库可用性](executable-clinical-guidelines/AVAILABILITY.md)
- [复现手册](executable-clinical-guidelines/REPRODUCE.md)
- [比较协议](executable-clinical-guidelines/protocols/RESEARCH_QUESTIONS.md)

初始化时保留LFS指针：

```bash
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init research/executable-clinical-guidelines
```

子仓库已包含独立综述、概念教程、逐研究证据与可用性账本、公开结果离线复算脚本、800例定位池和多组小切片。具体制品边界与待标注项目在子仓库说明；未开展新的LLM或临床比较实验。
