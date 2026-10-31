# LeetCode Review

从 Chrome 中已登录的 LeetCode 中国站读取已解决题目，为数组、链表、栈、二叉树、回溯算法各随机选一道，生成当天可作答的 Python 复习文件。

## 使用

1. 在 Chrome 中登录 `https://leetcode.cn/progress/`。
2. 在 Codex 中运行：

   ```text
   使用 $leetcode-review 生成今天的 LeetCode 复习
   ```

3. 技能会在当前工作目录生成 `review_YYYY-MM-DD.py`。

## 规则

- 图论搜索和动态规划暂不出题。
- 同一题 7 天内不会再次出现。
- 文件中先写入固定的 `ListNode`、`TreeNode` 和导入语句，再按题目写入题号、题名和 LeetCode Python 3 作答模板。

完整流程见 [SKILL.md](SKILL.md)，章节判定规则见 [chapter-classification.md](references/chapter-classification.md)。
