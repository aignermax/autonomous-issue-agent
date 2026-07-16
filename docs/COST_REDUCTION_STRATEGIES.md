# Cost Reduction Strategies

**Current situation:** €584/month for ~30 issues = €19.47/issue average

**Target:** Reduce to €200-300/month (50-60% cost reduction)

---

## 🎯 High-Impact Strategies (Implement First)

### 1. **Reduce MAX_TURNS Limit** (Est. savings: 30-40%)

**Current:** 500 turns per session
**Problem:** Complex issues like #267 used 14+ iterations
**Solution:**
```bash
# In .env
AGENT_MAX_TURNS=100  # Down from 500
```

**Impact:**
- Forces agent to be more efficient
- Prevents runaway iterations
- Complex issues may need manual continuation
- **Estimated savings: €175-230/month**

**Risk:** Agent might give up on complex issues → Solution: Manual restart if needed

---

### 2. **Add Token Budget per Issue** (Est. savings: 20-30%)

**Problem:** No budget limit → agent can spend unlimited on one issue
**Solution:** Add hard token limit per issue

```python
# In config.py
MAX_TOKENS_PER_ISSUE = 500_000  # ~€3 limit per issue
```

**Impact:**
- Caps worst-case cost at €3/issue
- Prevents expensive failures
- **Estimated savings: €115-175/month**

---

### 3. **Smart Context Selection** (Est. savings: 15-25%)

**Current:** Agent reads entire repository every time
**Problem:** Large repos → huge context → high cost
**Solution:** Use semantic search to pre-filter relevant files

```python
# Before Claude Code execution:
# 1. Use semantic_search.py to find relevant files
# 2. Pass only those files to Claude Code
# 3. Reduce context by 70-80%
```

**Impact:**
- Smaller context = cheaper iterations
- Faster execution
- **Estimated savings: €90-145/month**

---

## 💡 Medium-Impact Strategies

### 4. **Issue Complexity Classification** (Est. savings: 10-15%)

Create labels to pre-screen issues:
- `agent-task-simple` → Low turn limit (50 turns, <€1)
- `agent-task-medium` → Medium limit (150 turns, <€5)
- `agent-task-complex` → High limit (300 turns, <€15)

**Manual review before assigning complex tasks.**

---

### 5. **Prompt Optimization** (Est. savings: 5-10%)

**Current prompt likely too verbose.**

Audit `src/prompt_template.py`:
- Remove redundant instructions
- Use bullet points instead of paragraphs
- Reference docs instead of inlining them

**Potential savings: €30-60/month**

---

### 6. **Batch Similar Issues** (Est. savings: 10-20%)

Group related issues and process in one session:
- Issue #425, #426, #427 (docs cleanup) → One session
- Avoid reloading same context 3 times

---

## 🔧 Low-Impact but Easy Wins

### 7. **Disable Verbose Logging in Production**

```bash
AGENT_LOG_LEVEL=WARNING  # Instead of DEBUG
```
Small token savings in system prompts.

---

### 8. **Pre-commit Hooks to Prevent Bad Issues**

Issues that are:
- Too vague → Agent wastes tokens exploring
- Already fixed → Agent wastes time checking
- Out of scope → Agent tries and fails

Add GitHub issue templates with mandatory fields.

---

## 📊 Implementation Priority

### Phase 1 (This Week) - Target: 40% reduction
1. ✅ Set `AGENT_MAX_TURNS=100` in .env
2. ✅ Add `MAX_TOKENS_PER_ISSUE=500000` limit
3. ✅ Review and optimize prompt template

**Expected savings: €230/month → New cost: €350/month**

---

### Phase 2 (Next Week) - Target: 60% reduction
4. ⬜ Implement smart context selection with semantic search
5. ⬜ Add issue complexity labels
6. ⬜ Audit completed issues for patterns

**Expected savings: €350/month → New cost: €230/month**

---

### Phase 3 (Optional)
7. ⬜ Build custom Claude Code wrapper with fine-grained control
8. ⬜ Implement session resumption with cached state
9. ⬜ Use cheaper models for simple tasks (Haiku for docs updates)

---

## 🎁 Bonus: ROI Analysis

**Current cost:** €584/month for 30 issues

**If you hired a junior dev:**
- €3,000-4,000/month salary
- 30 issues = ~60 hours of work (2h/issue)
- **Cost per issue: €100-130**

**Agent cost per issue: €19.47**

**You're already saving ~80% vs. human developer!**

But yes, let's optimize it further to €7-10/issue (€200-300/month total).

---

## 📈 Monitoring

After implementing Phase 1, track:
- Average tokens per issue
- Issues hitting token/turn limits
- Success rate (PRs merged vs. failed attempts)

Add this to the dashboard!
