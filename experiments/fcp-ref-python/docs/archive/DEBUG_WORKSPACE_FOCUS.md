# Workspace Focus — Path Resolution & Security Fix

**Date:** 2026-03-20
**Issue:** Inconsistent workspace_focus root between haca-core and haca-evolve profiles
**Commit:** e7fd2d8 fix(workspace_focus): standardize path resolution across profiles

---

## Problem Analysis

### Original Issue

**haca-core profile:**
- workspace_focus boundary = `entity_root/workspace/` ✓

**haca-evolve profile:**
- workspace_focus boundary = `entity_root/` ❌ (WRONG)

This inconsistency meant:
- `/work set subdir` in haca-evolve would create/set focus to `entity_root/subdir`
- `/work set subdir` in haca-core would create/set focus to `entity_root/workspace/subdir`

### Root Cause

**operator.py line 558 (old):**
```python
boundary = layout.root if profile == "haca-evolve" else layout.workspace_dir
```

This profile-dependent logic was incorrect. The requirements specify that BOTH profiles should:
1. Allow relative paths (resolve against `entity_root/workspace/`)
2. Allow absolute paths outside entity_root (with security constraints)
3. Reject paths that are ancestors of entity_root

---

## Solution

### New Logic (Unified for Both Profiles)

**Path Resolution:**
```python
# Relative path (or ".") → resolve against entity_root/workspace/
if subdir in (".", ""):
    target = workspace_dir.resolve()
elif PathlibPath(subdir).is_absolute():
    # Absolute path → use as-is (validate security separately)
    target = PathlibPath(subdir).resolve()
else:
    # Relative path → resolve against workspace_dir
    target = (workspace_dir / subdir).resolve()
```

**Security Validation:**
```python
# Reject if target is an ancestor of entity_root
try:
    entity_root.relative_to(target)
    # If this succeeds, target IS an ancestor → REJECT
    print(f"path is an ancestor of entity root: {target}")
    return
except ValueError:
    # Good: target is NOT an ancestor of entity_root
    pass
```

### Security Rules

✅ **Allowed:**
- `/work set subdir` → `entity_root/workspace/subdir`
- `/work set .` → `entity_root/workspace/`
- `/work set /home/user/projects/my_project` → `/home/user/projects/my_project` (sibling directory)
- `/work set /tmp/workspace` → `/tmp/workspace` (external directory)

❌ **Rejected:**
- `/work set /` → Filesystem root (ancestor of entity_root)
- `/work set /home` → Parent directory (ancestor of entity_root)
- `/work set /home/estupendo/code` → Any ancestor of entity_root

---

## Test Coverage

Added `tests/test_workspace_focus.py` with 13 tests:

**Relative Paths (3 tests):**
- ✅ Relative subdir resolves against workspace_dir
- ✅ Dot (.) maps to workspace_dir
- ✅ Empty string maps to workspace_dir

**Absolute Paths (2 tests):**
- ✅ Absolute path outside entity_root allowed
- ✅ Absolute path inside workspace allowed

**Security Validation (4 tests):**
- ✅ Reject entity_root as target
- ✅ Reject parent of entity_root
- ✅ Reject filesystem root (/)
- ✅ Allow sibling directory (not ancestor)

**Nested Paths (2 tests):**
- ✅ Nested relative paths resolve correctly
- ✅ Relative paths with `..` normalize correctly

**Profiles (2 tests):**
- ✅ haca-core uses unified validation
- ✅ haca-evolve uses unified validation

**Result:** All 13 tests passing ✓

---

## Code Changes

### File: `fcp_base/operator.py`

**Removed:**
```python
# Profile-dependent boundary (WRONG)
boundary = layout.root if profile == "haca-evolve" else layout.workspace_dir
target = (boundary / subdir).resolve() if subdir not in (".", "") else boundary.resolve()
try:
    target.relative_to(boundary)
except ValueError:
    print(f"  path outside {'entity root' if profile == 'haca-evolve' else 'workspace'}: {subdir}")
    return
```

**Added:**
```python
# Unified path resolution logic
entity_root = layout.root
workspace_dir = layout.workspace_dir

if subdir in (".", ""):
    target = workspace_dir.resolve()
elif PathlibPath(subdir).is_absolute():
    target = PathlibPath(subdir).resolve()
else:
    target = (workspace_dir / subdir).resolve()

# Security: reject ancestors of entity_root
try:
    entity_root.relative_to(target)
    print(f"  path is an ancestor of entity root: {target}")
    return
except ValueError:
    pass  # Good: target is NOT an ancestor
```

**Also updated:**
- Help text: `/work set <subdir>` → `/work set <subdir> (within entity_root/workspace/)`
- Help text: Added `/work set .` → `set focus to entity_root/workspace/`
- Usage message: "clear" → "unset" (consistency)

---

## Impact

### Before
| Profile | Relative Path | Absolute Path | Ancestor Check |
|---------|---------------|---------------|-----------------|
| haca-core | entity_root/workspace/ ✓ | N/A | N/A |
| haca-evolve | entity_root/ ❌ | N/A | N/A |

### After
| Profile | Relative Path | Absolute Path | Ancestor Check |
|---------|---------------|---------------|-----------------|
| haca-core | entity_root/workspace/ ✓ | ✓ Allowed | ✓ Reject |
| haca-evolve | entity_root/workspace/ ✓ | ✓ Allowed | ✓ Reject |

---

## Behavior Examples

**haca-core (before):**
```
/work set myproject  → entity_root/workspace/myproject ✓
/work set .          → entity_root/workspace/ ✓
/work set /tmp/ext   → ERROR (outside workspace)
```

**haca-evolve (before):**
```
/work set myproject  → entity_root/myproject ❌ (WRONG)
/work set .          → entity_root/ ❌ (WRONG)
/work set /tmp/ext   → /tmp/ext ❌ (allowed but entity_root is not protected)
```

**Both profiles (after):**
```
/work set myproject  → entity_root/workspace/myproject ✓
/work set .          → entity_root/workspace/ ✓
/work set /tmp/ext   → /tmp/ext ✓ (allowed, entity_root is not ancestor)
/work set /          → ERROR (ancestor of entity_root)
/work set /home      → ERROR (ancestor of entity_root)
```

---

## Test Results

```
============================== 224 passed in 9.14s ==============================
13 new tests (workspace_focus) + 211 existing tests, 0 regressions
```

---

## Files Changed

1. **fcp_base/operator.py**
   - Replaced profile-dependent boundary with unified logic
   - Added path type detection (relative vs absolute)
   - Added ancestor validation
   - Updated help text and error messages

2. **tests/test_workspace_focus.py** (NEW)
   - 13 comprehensive security tests
   - Covers all path resolution scenarios
   - Validates security constraints for both profiles

---

## Verification Checklist

- [x] Profile-dependent logic removed
- [x] Relative paths resolve against entity_root/workspace/
- [x] Absolute paths allowed with ancestor validation
- [x] "/work set ." maps to entity_root/workspace/
- [x] Ancestors of entity_root are rejected
- [x] Both profiles use identical validation
- [x] 13 new tests all passing
- [x] No regressions (224/224 tests passing)
- [x] Help text updated with examples
- [x] Code review ready (clean diff, single responsibility)
