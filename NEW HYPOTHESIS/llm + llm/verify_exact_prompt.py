import os
import sys
import hashlib
import difflib

# Add current folder to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import STAGE1_SYSTEM_PROMPT, RESOURCE_COLUMNS, RESOURCE_DESC_TEXT

def verify():
    eval_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "evaluate_resources.py"))
    if not os.path.exists(eval_file):
        print(f"Error: Could not find {eval_file}")
        return False

    with open(eval_file, "r", encoding="utf-8") as f:
        eval_lines = f.readlines()

    # Extract lines 427-437 for resource_desc
    # Note: 1-indexed line 427 is index 426
    # Let's dynamically locate query_groq_llm and extract resource_desc & system_prompt
    # evaluate_resources.py lines 427-453 (0-indexed: 426 to 453)
    slice_lines = eval_lines[426:453]
    import textwrap
    scope = {}
    code_str = textwrap.dedent("".join(slice_lines))
    exec(code_str, scope)
    orig_system_prompt = scope.get("system_prompt")
    orig_resource_desc = scope.get("resource_desc")

    hash_orig_sys = hashlib.sha256(orig_system_prompt.encode("utf-8")).hexdigest()
    hash_new_sys = hashlib.sha256(STAGE1_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

    hash_orig_desc = hashlib.sha256(orig_resource_desc.encode("utf-8")).hexdigest()
    hash_new_desc = hashlib.sha256(RESOURCE_DESC_TEXT.encode("utf-8")).hexdigest()

    sys_match = (hash_orig_sys == hash_new_sys)
    desc_match = (hash_orig_desc == hash_new_desc)

    print("=================================================================")
    print("PROMPT & RESOURCE DEFINITION BYTE-IDENTICAL VERIFICATION")
    print("=================================================================")
    print(f"Original system_prompt SHA256: {hash_orig_sys}")
    print(f"Pipeline system_prompt SHA256: {hash_new_sys}")
    print(f"System prompt match: {'IDENTICAL (100% byte match)' if sys_match else 'MISMATCH'}")
    print("-----------------------------------------------------------------")
    print(f"Original resource_desc SHA256: {hash_orig_desc}")
    print(f"Pipeline resource_desc SHA256: {hash_new_desc}")
    print(f"Resource desc match: {'IDENTICAL (100% byte match)' if desc_match else 'MISMATCH'}")
    print("=================================================================")

    if not sys_match:
        diff = list(difflib.unified_diff(
            orig_system_prompt.splitlines(keepends=True),
            STAGE1_SYSTEM_PROMPT.splitlines(keepends=True),
            fromfile="evaluate_resources.py",
            tofile="constants.py"
        ))
        print("Diff found in system_prompt:")
        sys.stdout.writelines(diff)
        return False

    return True

if __name__ == "__main__":
    verify()
