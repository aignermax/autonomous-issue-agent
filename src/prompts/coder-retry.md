Reviewer found issues on your PR for issue #{issue_number}.

## Reviewer Verdict: BLOCKING
{review_summary}

## Reviewer Findings
{findings_text}

## Your Task

Address every BLOCKING finding above. NIT findings are optional but
appreciated. Use the same tools as before:
- `{tools_python} {tools_dir}/semantic_search.py "..."` to locate code
- `{tools_python} {tools_dir}/build_errors.py --suggest-fixes` for build issues
- `{tools_python} {tools_dir}/smart_test.py` to run tests

After fixing, commit and push to the same branch (`{branch}`). The reviewer
will re-run automatically.

## Original Issue
{issue_title}

{issue_body}
