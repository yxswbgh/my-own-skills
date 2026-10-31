---
name: leetcode-review
description: 从 Chrome 中已登录的 LeetCode 中国站进度页读取已解决的题目，按数组、链表、栈、二叉树、回溯算法各随机选一道，生成带固定 Python 头部的每日复习文件，并确保同一题 7 天内不重复。适用于“做今天的 LeetCode 复习”“抽题复习”或“生成 review_日期.py”的请求。
---

# LeetCode Review

从用户已经登录的 Chrome 会话中收集 LeetCode 中国站已解决题目，为已学章节抽题，并在本地生成可直接作答的 Python 复习文件。

## 操作边界

- 用 `$computer-use` 操作用户现有的 Chrome。不要要求密码、复制 Cookie、读取浏览器令牌，也不要绕过登录。
- 在 LeetCode 页面上只读：可以浏览、滚动、切换筛选和复制题目模板，不提交答案、不改题目状态、不关闭用户已有标签页。
- 默认只出这五章：`数组`、`链表`、`栈`、`二叉树`、`回溯算法`。`图论搜索` 和 `动态规划` 当前未学习，不得出题。
- 本地默认写入当前工作目录；如果用户指定目录，以用户指定目录为准。
- 同日文件已经存在时先检查，不要自动覆盖。只有用户明确要求重新生成时，才可覆盖。

## 输出契约

生成 `review_YYYY-MM-DD.py`。固定开头必须逐字为：

```python
from typing import Optional,List
from collections import deque

class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
```

每个选中题目接着写：

```python
# 题号. 题目中文名称
class Solution:
    def 函数名(self, 参数: 类型) -> 返回类型:
```

标题中保留题号和页面显示的中文题名。代码区只放 LeetCode 的 Python 3 默认作答模板：保留 `class Solution`、主函数签名、题目模板要求的嵌套结构或辅助方法；不要复制题目描述、示例、解释、测试用例、Markdown 围栏、提交结果或页面上的解答。

## 工作流

### 1. 收集已解决问题

1. 在现有 Chrome 中打开 `https://leetcode.cn/progress/`，等待题目列表完全加载。
2. 持续滚动、展开或翻页，直到题目数量和链接集合不再增加。以页面标记为已解决/通过且带有 `/problems/<slug>/` 链接的题目为准；不要把排行榜、推荐题或未做题目混入。
3. 收集题目题号、中文标题、slug、完整链接和标签。滚动后重新合并去重。
4. 按 [章节判定规则](references/chapter-classification.md) 为每道题指定一个主章节。无法可靠归入前五章的题目直接跳过。
5. 将候选题目写入临时 JSON。只包含五章中的题目，格式见下文。

如果进度页暂时不显示逐题列表，先使用页面自带的筛选、展开和“显示更多”控件。不要为了取数而改用第三方站点，也不要声称已经拿到未实际看到的题目。

### 2. 随机抽题与 7 天去重

在技能目录中运行：

下面的 `python` 表示当前可执行的 Python 3 解释器。若 Windows 上的 `python` 是 Microsoft Store 占位符或直接启动失败，先用当前 Codex 环境提供的 Python 路径或系统 `py` 启动器定位真实解释器，再替换命令中的 `python`。两个脚本只依赖标准库。

```bash
python scripts/select_reviews.py \
  --candidates <候选题目.json> \
  --output-dir <复习文件目录> \
  --date YYYY-MM-DD \
  --plan <当天计划.json>
```

脚本会：

- 每章随机选一道，并保证同一批题目不重复；
- 扫描输出目录已有的 `review_YYYY-MM-DD.py`，跳过过去 7 个日历日内出现过的题号；
- 只有在五章都能选到题时生成 `status: "ready"` 的计划；
- 如果某章无可用题目，写出 `status: "incomplete"` 的计划并以非零状态退出。

不要用人工选择绕过冷却。若计划不完整，报告缺失章节，并回到 Chrome 扩大已解决题目集合或请用户处理，不要生成缺题文件。

### 3. 获取作答模板

逐题打开计划中的链接：

1. 核对题号和中文题名。
2. 切换到 Python 3 代码模板，等待编辑器加载。
3. 只复制默认 `class Solution` 模板。链表题使用文件顶部的统一 `ListNode`；二叉树题使用统一 `TreeNode`。
4. 将模板写入临时 `starters.json`，键使用题号。

如果页面没有 Python 3、模板未加载、题号与标题不一致，或拿不到完整签名，停止生成并说明具体题目。不要凭记忆补造签名。

### 4. 生成并检查

运行：

```bash
python scripts/render_review.py \
  --plan <当天计划.json> \
  --starters <作答模板.json> \
  --output-dir <复习文件目录>
```

生成后检查：

- 固定代码块位于文件第一行且只出现一次；
- 正好有五个题目标题，五章各一个，题号没有重复；
- 每个标题后都是 `class Solution`，没有 Markdown 围栏或题目描述；
- 文件名为 `review_YYYY-MM-DD.py`，日期来自用户当前日期，时区为 `Asia/Shanghai`；
- 图中最后两章没有出现在文件中；
- 同一题号没有出现在当前日期及之前 6 天的任一 `review_*.py` 中。

成功后删除本次创建的候选、计划和作答模板临时文件。文件已经存在时，`render_review.py` 会拒绝覆盖；不要添加 `--overwrite`，除非用户在看过现有文件后明确要求。

最终只报告生成文件路径、五道题及章节。若流程未完整成功，明确说明停在哪一步，不要用部分结果冒充完成。

## 临时 JSON 格式

候选文件：

```json
{
  "candidates": [
    {
      "chapter": "数组",
      "number": "1",
      "title": "两数之和",
      "slug": "two-sum",
      "url": "https://leetcode.cn/problems/two-sum/"
    }
  ]
}
```

作答模板文件：

```json
{
  "1": "class Solution:\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\n        pass"
}
```

这些 JSON 是中间文件，不属于最终交付物。
