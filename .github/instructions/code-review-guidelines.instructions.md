---
description: "Code review guidelines and what to focus on during reviews"
---

# Code Review Guidelines

## What NOT to Comment On

**When reviewing code, do NOT comment on:**

- **Missing imports** - We use static analysis tooling to catch that
- **Code formatting** - We have ruff as a formatting tool that will catch those if needed (unless specifically instructed otherwise in these instructions)

## What TO Comment On

**When reviewing code, DO comment on:**

- **Blind exception catching** (BLE001) - Must use specific exceptions
- **Unused imports** (F401) - Should be removed immediately
- **Import sorting** (I001) - Must follow alphabetical grouping
- **Security violations** (S) - Avoid unsafe patterns like `eval()`
- **Complexity issues** (C901) - Functions should be simple and readable

## Performance Considerations

During code reviews, check for:

- [ ] Are there any obvious algorithmic inefficiencies (O(n^2) or worse)?
- [ ] Are data structures appropriate for their use?
- [ ] Are there unnecessary computations or repeated work?
- [ ] Is caching used where appropriate, and is invalidation handled correctly?
- [ ] Are database queries optimized, indexed, and free of N+1 issues?
- [ ] Are large payloads paginated, streamed, or chunked?
- [ ] Are there any memory leaks or unbounded resource usage?
- [ ] Are network requests minimized, batched, and retried on failure?
- [ ] Are assets optimized, compressed, and served efficiently?
- [ ] Are there any blocking operations in hot paths?
- [ ] Is logging in hot paths minimized and structured?
- [ ] Are performance-critical code paths documented and tested?
- [ ] Are there automated tests or benchmarks for performance-sensitive code?
- [ ] Are there alerts for performance regressions?
- [ ] Are there any anti-patterns (e.g., SELECT *, blocking I/O, global variables)?

## Security Review Points

- **Access Control**: Verify proper authorization checks
- **Input Validation**: Ensure all user inputs are validated and sanitized
- **Cryptographic Operations**: Use modern, secure algorithms
- **Secret Management**: No hardcoded secrets, use environment variables or secret stores
- **SQL Injection**: Use parameterized queries only
- **XSS Prevention**: Proper output encoding for user data
- **Error Handling**: Don't expose sensitive information in error messages
