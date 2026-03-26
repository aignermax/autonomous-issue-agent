# Smart Test

Run tests with filtered, readable output.

## Instructions

Run the smart test tool with optional filter:

```bash
python3 ~/.cap-tools/smart_test.py [filter]
```

Show the compact summary. If tests fail, analyze the detailed output.

## Examples

- `/test` - All tests, compact summary
- `/test ParameterSweeper` - Only ParameterSweeper tests
- `/test BoundingBox` - Only BoundingBox tests
- `/test --file MyFeatureTests.cs` - Specific test file

Output shows summary (17 lines) instead of all 1193 test results!
