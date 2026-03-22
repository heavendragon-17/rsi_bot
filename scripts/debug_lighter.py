import sys

import pkg_resources

print("Python Executable:", sys.executable)
print("Path:", sys.path)

print("\nInstalled Packages (lighter*):")
for p in pkg_resources.working_set:
    if "lighter" in p.project_name.lower():
        print(f"{p.project_name}=={p.version}")

print("\nAttempting Imports:")
try:
    import lighter

    print("SUCCESS: import lighter")
    print("lighter file:", lighter.__file__)
    print("lighter dir:", dir(lighter))
except ImportError as e:
    print("FAILED: import lighter ->", e)

try:
    import lighter_sdk

    print("SUCCESS: import lighter_sdk")
    print("lighter_sdk file:", lighter_sdk.__file__)
except ImportError as e:
    print("FAILED: import lighter_sdk ->", e)

try:
    import lighter_python  # noqa: F401

    print("SUCCESS: import lighter_python")
except ImportError as e:
    print("FAILED: import lighter_python ->", e)
