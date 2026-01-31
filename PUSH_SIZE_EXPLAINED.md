# Why the Git push is so large (~11 MB, 4800+ objects)

## What we found

1. **History contains `.venv/`**  
   Your **first commit** (`9cda00c initial commit`) added the whole `.venv/` folder.  
   Later you ran "Stop tracking .venv; add .gitignore", so the **current** tree no longer has `.venv`, but **old commits still do**.  
   When you push, Git sends **all objects** from **all commits**. So it still uploads:
   - `.venv/lib/.../pymupdf/libmupdf.dylib` (~31 MB)
   - `.venv/.../pymupdf/_mupdf.so` (~12 MB)
   - Plus thousands of other `.venv` files  
   That’s why the push is ~11+ MB and 4800+ objects.

2. **Current tree still tracks `__pycache__/`**  
   `.gitignore` has `__pycache__/`, but those files were committed earlier, so they’re still in the index.  
   They’re not huge, but they shouldn’t be in the repo.

## What was done

- **Stopped tracking `__pycache__/`** and re-staged only non-ignored files (`git rm -r --cached .` then `git add .`).  
  You need to **commit** that change.

## How to get a small push

Because `.venv` is in **history**, the only way to make the **next push** small is to **drop that history** and push a single clean commit:

```bash
cd "/Users/dinalbandara/Desktop/IIT/4th year/FYP/PROJECT/BACKEND"

git checkout --orphan temp-main
git add -A
git commit -m "Initial commit: Crackint backend (no venv, no pycache)"
git branch -D main
git branch -m main
git push --set-upstream origin main --force
```

After that, the repo on GitHub will have one commit and a small push (only your app code).  
If you prefer to **keep history** and don’t mind one slow push, use:

```bash
git config http.postBuffer 524288000
git push --set-upstream origin main
```

and wait for it to finish.
