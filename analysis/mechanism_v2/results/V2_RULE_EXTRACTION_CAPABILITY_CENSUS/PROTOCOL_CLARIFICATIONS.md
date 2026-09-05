# 执行前的单位与 schema 澄清

以下澄清于源清单冻结、匹配输出之前告知全部来源审核员；不修改原协议或重新抽样。

1. 实际浅层逻辑枚举为 `all / any / at_least_n`。它并非完全没有连词表示；问题是连词与计数被混在一个字段，且没有独立组效力、NOT、递归子节点、计数域、分支适用条件或权重程序。
2. 原子 relation 枚举：feature_of、required_for、sufficient_for、pathognomonic_for、excludes、argues_against、distinguishes_from、variant_of、synonym_of、caused_by、treated_by。另有极性、模态、阈值、comparator/context 和短名词性 predicate。
3. 同质浅层组可通过一致的成员 relation 隐式表示共同效力；不得仅因执行器实现有错而将其原始表示判为失真。反之，独立目标拼成组或不同作用的成员被混合，不能因为各原子“各自说对了”就判完整输出组忠实。
4. 相同连词的文本嵌套可化简；不能把 `A OR (B OR C)` 冒充必然不可表达。真正问题是混合连词、条件内嵌、NOT/计数作用域与嵌套作用域。
5. 明确疾病的弱表型/流行病学关联可计入目标；纯分子机制、治疗/检查建议、无明确对象的索引名词列表单列。`variant_of` 可表示独立分类定义，但不得为标题或列表杜撰标准。

固定复审子集：按 `SHA256(seed + '|R|' + sample_id)` 排序选取来源窗口 8 个、输出单元 24 个，在任何判定完成前生成 `review_selection.json`。另外复审所有疑似严格幻觉、来源未决和初判忠实的输出组。保留初判与复审文件，不覆盖原记录。
