#!/usr/bin/env python3
"""
MC Fabric Mod Architect — Automatic Fabric Mod Maker
Browser-only mode. No API keys needed. Self-healing.
Supports PC and GitHub Codespace environments.
"""

import os
import sys
import json
import glob
import time
import shutil
import subprocess
import threading
import requests
import platform
import re
import zipfile
import io

if sys.version_info < (3, 8):
    print("Python 3.8+ required.")
    sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

CONFIG_PATH = os.path.join(os.path.expanduser("~"), "fabric_architect_config.json")
if IS_WINDOWS:
    os.system("")

sys.stdout.write("\x1b]2;MC Fabric Mod Architect\x07")
sys.stdout.flush()

C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_DARK_GRAY = "\033[90m"
C_MAGENTA = "\033[95m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

EXCLUDED_DIRS = {".git", ".gradle", ".idea", "target", "build", "gradle", "out", "bin", ".loom", "mods", "workspaces"}

_last_session = {
    "provider": None, "model": None, "api_key": None,
    "system_instruction": None, "max_tokens": None,
    "mc_version": None, "build_tool": "Gradle",
    "project_dir": None, "build_failed": False,
    "config": None, "heal_attempt_count": 0,
    "previous_errors": [], "mod_id": None,
    "mod_class_name": None, "pkg": None,
    "expected_main_path": None, "java_version": None,
    "version_info": None, "is_codespace": False,
}

# =================================================================
# FABRIC VERSION DATABASE — PINNED STABLE RELEASES
# =================================================================

FABRIC_VERSION_DB = {
    "1.21.4": {"loader": "0.16.9", "yarn": "1.21.4+build.1", "fabric_api": "0.112.2+1.21.4", "loom": "1.7.4", "gradle": "8.10", "java": 21, "data_components": True, "identifier_of": True, "registries_class": True},
    "1.21.3": {"loader": "0.16.7", "yarn": "1.21.3+build.2", "fabric_api": "0.106.0+1.21.3", "loom": "1.7.4", "gradle": "8.10", "java": 21, "data_components": True, "identifier_of": True, "registries_class": True},
    "1.21.1": {"loader": "0.16.5", "yarn": "1.21.1+build.3", "fabric_api": "0.105.0+1.21.1", "loom": "1.7.4", "gradle": "8.10", "java": 21, "data_components": True, "identifier_of": True, "registries_class": True},
    "1.20.6": {"loader": "0.16.0", "yarn": "1.20.6+build.1", "fabric_api": "0.100.0+1.20.6", "loom": "1.6.12", "gradle": "8.7", "java": 21, "data_components": True, "identifier_of": False, "registries_class": False},
    "1.20.4": {"loader": "0.15.11", "yarn": "1.20.4+build.3", "fabric_api": "0.97.2+1.20.4", "loom": "1.5.12", "gradle": "8.5", "java": 17, "data_components": False, "identifier_of": False, "registries_class": False},
    "1.20.1": {"loader": "0.15.11", "yarn": "1.20.1+build.10", "fabric_api": "0.92.2+1.20.1", "loom": "1.4.6", "gradle": "8.3", "java": 17, "data_components": False, "identifier_of": False, "registries_class": False},
}


def resolve_version_info(mc_version):
    info = FABRIC_VERSION_DB.get(mc_version)
    if info:
        return info.copy()
    inferred = _infer_version_defaults(mc_version)
    fetched = _fetch_fabric_versions(mc_version)
    if fetched:
        for key in ["loader", "yarn", "fabric_api"]:
            if key in fetched:
                inferred[key] = fetched[key]
    return inferred

def _infer_version_defaults(mc_version):
    vf = 1.20
    try:
        parts = mc_version.split(".")
        if len(parts) >= 2: vf = float(f"{parts[0]}.{parts[1]}")
    except ValueError: pass
    java = 21 if vf >= 1.205 else (17 if vf >= 1.17 else 16)
    return {"loader": "0.16.9", "yarn": f"{mc_version}+build.1", "fabric_api": f"0.100.0+{mc_version}", "loom": "1.7.4", "gradle": "8.10", "java": java, "data_components": vf >= 1.205, "identifier_of": vf >= 1.212, "registries_class": vf >= 1.212}

def _fetch_fabric_versions(mc_version):
    result = {}
    try:
        res = requests.get(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}", timeout=10)
        if res.status_code == 200 and res.json(): result["loader"] = res.json()[0]["loader"]["version"]
    except Exception: pass
    try:
        import xml.etree.ElementTree as ET
        res = requests.get("https://maven.fabricmc.net/net/fabricmc/yarn/maven-metadata.xml", timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            versions = [v.text for v in root.findall(".//version")]
            matching = [v for v in versions if v.startswith(mc_version)]
            if matching: result["yarn"] = matching[-1]
    except Exception: pass
    try:
        import xml.etree.ElementTree as ET
        res = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/maven-metadata.xml", timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            versions = [v.text for v in root.findall(".//version")]
            matching = [v for v in versions if mc_version in v]
            if matching: result["fabric_api"] = matching[-1]
    except Exception: pass
    return result

# =================================================================
# FABRIC RULES & PARSER (Condensed for space, same logic)
# =================================================================

HARDCODED_FABRIC_MISTAKES = (
    "MANDATORY FABRIC RULES:\n1. ModInitializer: MUST implement onInitialize().\n2. fabric.mod.json: MUST include schemaVersion, id, version, entrypoints, depends.\n3. 1.20.5+: ItemStack.getTag() REMOVED. Use Data Components.\n4. 1.21.2+: new Identifier() REMOVED. Use Identifier.of().\n5. 1.21.2+: Use Registries class NOT Registry.ITEM.\n6. ALWAYS use Yarn mappings.\n7. Client code in client entrypoint ONLY.\n8. NEVER use Bukkit APIs.\n"
)

def generate_fabric_version_constraints(mc_version, version_info):
    c = [f"TARGET: Fabric MC v{mc_version}", f"Java {version_info['java']}"]
    if version_info.get("data_components"): c.append("- DATA COMPONENTS: Use Data Components, NOT NBT.")
    else: c.append("- NBT: Use ItemStack.getTag()/getOrCreateTag().")
    if version_info.get("identifier_of"): c.append("- Identifier: Use Identifier.of(). new Identifier() DOES NOT EXIST.")
    else: c.append("- Identifier: Use new Identifier().")
    if version_info.get("registries_class"): c.append("- Registries: Use Registries.ITEM. Registry.register(Registries.ITEM, ...)")
    else: c.append("- Registries: Use Registry.ITEM.")
    return "\n".join(c)

def parse_ai_response(raw_text, expected_main_path=None, pkg_structure=None, mod_class_name=None, mod_id=None):
    files_to_write = {}; lines = raw_text.splitlines(); current_file = None; current_content = []
    for line in lines:
        ls = line.strip()
        if ls.startswith("================ FILE:") and ls.endswith("================"):
            current_file = ls.replace("================ FILE:", "").replace("================", "").strip(); current_content = []; continue
        if ls == "================ END ================":
            if current_file: files_to_write[current_file] = clean_markdown_block("\n".join(current_content)); current_file = None
            continue
        if current_file is not None: current_content.append(line)
    if not files_to_write:
        current_block = None; current_lang = None; current_content = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") and current_block is None: current_lang = stripped[3:].strip().lower(); current_content = []; current_block = True; continue
            if stripped == "```" and current_block is not None:
                code = clean_markdown_block("\n".join(current_content))
                fname = infer_filename(code, current_lang, expected_main_path, pkg_structure, mod_class_name, mod_id)
                if fname and code.strip(): files_to_write[fname] = code
                current_block = None; current_lang = None; current_content = []; continue
            if current_block is not None: current_content.append(line)
    if not any("fabric.mod.json" in f for f in files_to_write):
        for jm in re.findall(r'(\{[\s\S]*?"schemaVersion"[\s\S]*?\})', raw_text):
            if "entrypoints" in jm: files_to_write["src/main/resources/fabric.mod.json"] = clean_markdown_block(jm); break
    return files_to_write

def infer_filename(code, lang, expected_main_path=None, pkg_structure=None, mod_class_name=None, mod_id=None):
    s = code.strip()
    if not s: return None
    if '"schemaVersion"' in s and '"entrypoints"' in s: return "src/main/resources/fabric.mod.json"
    if '"compatibilityLevel"' in s and '"mixins"' in s and mod_id: return f"src/main/resources/{mod_id}.mixins.json"
    if "plugins {" in s and "loom" in s.lower(): return "build.gradle"
    if s.strip().startswith("org.gradle") and "class " not in s: return "gradle.properties"
    if "pluginManagement" in s and "class " not in s: return "settings.gradle"
    if "package " in s:
        pkg_match = re.search(r'package\s+([\w.]+)\s*;', s)
        if pkg_match:
            cls_match = re.search(r'public\s+(?:class|interface|enum)\s+(\w+)', s)
            if cls_match: return f"src/main/java/{pkg_match.group(1).replace('.', '/')}/{cls_match.group(1)}.java"
    return None

def clean_markdown_block(content):
    content = content.strip()
    if content.startswith("```"): lines = content.splitlines(); lines = lines[1:]; content = "\n".join(lines)
    if content.endswith("```"): lines = content.splitlines(); lines = lines[:-1]; content = "\n".join(lines)
    return content.strip()

# =================================================================
# AUTO FIXES
# =================================================================

def auto_fix_identifier_usage(project_dir, version_info):
    if not version_info.get("identifier_of"): return []
    fixes = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith(".java"): continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f: content = f.read()
                if "new Identifier(" in content:
                    content = re.sub(r'new\s+Identifier\s*\(', 'Identifier.of(', content)
                    with open(filepath, "w", encoding="utf-8") as f: f.write(content)
                    fixes.append(f"Fixed Identifier in {file}")
            except Exception: pass
    return fixes

def auto_fix_registries_usage(project_dir, version_info):
    if not version_info.get("registries_class"): return []
    fixes = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith(".java"): continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f: content = f.read()
                modified = False
                for field in ["ITEM", "BLOCK", "ENCHANTMENT", "ENTITY_TYPE"]:
                    if f"Registry.{field}" in content: content = content.replace(f"Registry.{field}", f"Registries.{field}"); modified = True
                if modified:
                    if "import net.minecraft.registry.Registries;" not in content: content = "import net.minecraft.registry.Registries;\n" + content
                    with open(filepath, "w", encoding="utf-8") as f: f.write(content)
                    fixes.append(f"Fixed Registries in {file}")
            except Exception: pass
    return fixes

def run_precompilation_fixes(project_dir, mod_id, mod_name, pkg, mod_class_name, mc_version, version_info):
    fixes = []
    fixes.extend(ensure_build_files(project_dir, mod_id, version_info, mc_version, _last_session.get("is_codespace", False)))
    fixes.extend(auto_fix_identifier_usage(project_dir, version_info))
    fixes.extend(auto_fix_registries_usage(project_dir, version_info))
    for fix in fixes: print(f"  -> {C_YELLOW}Auto-Fix:{C_RESET} {fix}")

# =================================================================
# CLIPBOARD & BROWSER
# =================================================================

def copy_to_clipboard(text):
    try:
        if IS_WINDOWS:
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE); process.communicate(text.encode('utf-8')); return True
        else:
            try:
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE); process.communicate(text.encode('utf-8')); return True
            except Exception: return False
    except Exception: return False

def execute_browser_request(system_instruction, prompt_text, project_dir, is_heal=False):
    full_prompt = f"SYSTEM INSTRUCTIONS:\n{system_instruction}\n\nUSER REQUEST:\n{prompt_text}"
    clipboard_ok = copy_to_clipboard(full_prompt)
    prompt_path = os.path.join(project_dir, "prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f: f.write(full_prompt)
    mode_label = "HEALING" if is_heal else "GENERATION"
    print(f"\n{C_GREEN}{C_BOLD}=== BROWSER MODE: {mode_label} ==={C_RESET}")
    if clipboard_ok: print(f"{C_GREEN}[OK] Prompt COPIED TO CLIPBOARD!{C_RESET}")
    else: print(f"{C_YELLOW}[!] Copy prompt.txt manually.{C_RESET}")
    print(f"{C_CYAN}[i] Prompt saved to: {C_WHITE}{prompt_path}{C_RESET}")
    print(f"  1. Open AI in browser\n  2. Paste prompt\n  3. Copy response\n  4. Save to: {C_YELLOW}{os.path.join(project_dir, 'response.txt')}{C_RESET}\n  5. Press Enter here")
    while True:
        input(f"\n{C_BOLD}{C_CYAN}Press Enter after saving response.txt...{C_RESET}")
        response_path = os.path.join(project_dir, "response.txt")
        if not os.path.exists(response_path): print(f"{C_RED}[!] NOT FOUND{C_RESET}"); continue
        try:
            with open(response_path, "r", encoding="utf-8") as f: raw_text = f.read()
            if not raw_text.strip(): continue
            try: os.remove(response_path)
            except Exception: pass
            return raw_text
        except Exception: continue

# =================================================================
# BUILD TOOLS (FIXED FOR CODESPACE)
# =================================================================

def get_subprocess_env(config):
    env = os.environ.copy()
    java_home = config.get("java_home", "").strip()
    if java_home and os.path.isdir(java_home):
        env["JAVA_HOME"] = java_home
        bin_dir = os.path.join(java_home, "bin")
        if os.path.isdir(bin_dir): env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")
    return env

def resolve_gradle_command(config, project_dir=None):
    if project_dir:
        g = os.path.join(project_dir, "gradlew.bat" if IS_WINDOWS else "gradlew")
        if os.path.isfile(g):
            if not IS_WINDOWS:
                try: os.chmod(g, 0o755)
                except Exception: pass
            return g
    return os.path.join(project_dir or ".", "gradlew.bat" if IS_WINDOWS else "gradlew")

def setup_gradle_wrapper(project_dir, config, gradle_version="8.10"):
    gradlew = os.path.join(project_dir, "gradlew.bat" if IS_WINDOWS else "gradlew")
    wrapper_jar = os.path.join(project_dir, "gradle", "wrapper", "gradle-wrapper.jar")
    if os.path.isfile(gradlew) and os.path.isfile(wrapper_jar): return True
    wrapper_dir = os.path.join(project_dir, "gradle", "wrapper"); os.makedirs(wrapper_dir, exist_ok=True)
    global_cache = os.path.join(os.path.expanduser("~"), ".fabric_architect_cache"); os.makedirs(global_cache, exist_ok=True)
    cached_jar = os.path.join(global_cache, "gradle-wrapper.jar")
    props = os.path.join(wrapper_dir, "gradle-wrapper.properties")
    with open(props, "w") as f: f.write(f"distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip\nnetworkTimeout=10000\nvalidateDistributionUrl=true\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n")
    if os.path.isfile(cached_jar) and os.path.getsize(cached_jar) > 10000:
        shutil.copy2(cached_jar, wrapper_jar)
    else:
        print(f"  {C_CYAN}[i] Downloading gradle-wrapper.jar...{C_RESET}")
        jar_url = "https://raw.githubusercontent.com/gradle/gradle/master/gradle/wrapper/gradle-wrapper.jar"
        try:
            r = requests.get(jar_url, timeout=30)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(cached_jar, "wb") as f: f.write(r.content)
                shutil.copy2(cached_jar, wrapper_jar)
            else: raise Exception("Bad download")
        except Exception:
            _download_and_extract_wrapper_jar(wrapper_jar, gradle_version)
            if os.path.isfile(wrapper_jar): shutil.copy2(wrapper_jar, cached_jar)
    _write_gradlew_bat(project_dir); _write_gradlew_unix(project_dir)
    return os.path.isfile(wrapper_jar)

def _download_and_extract_wrapper_jar(wrapper_jar, gradle_version):
    zip_url = f"https://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip"
    try:
        r = requests.get(zip_url, timeout=120, stream=True); chunks = []
        for chunk in r.iter_content(chunk_size=8192): chunks.append(chunk)
        with zipfile.ZipFile(io.BytesIO(b''.join(chunks))) as zf:
            for name in zf.namelist():
                if name.endswith("gradle-wrapper.jar"):
                    with zf.open(name) as src, open(wrapper_jar, "wb") as dst: dst.write(src.read())
                    return
    except Exception as e: print(f"  {C_RED}[!] Failed: {e}{C_RESET}")

def _write_gradlew_bat(project_dir):
    # Removed DEFAULT_JVM_OPTS that caused "could not find Xmx64m" errors in some shells
    content = r"""@rem
@if "%DEBUG%"=="" @echo off
set DIRNAME=%~dp0
if "%DIRNAME%"=="" set DIRNAME=.
set APP_HOME=%DIRNAME%
for %%i in ("%APP_HOME%") do set APP_HOME=%%~fi

if defined JAVA_HOME goto findJavaFromJavaHome
set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if %ERRORLEVEL% equ 0 goto execute
echo ERROR: JAVA_HOME is not set and no 'java' command could be found. 1>&2
goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe
if exist "%JAVA_EXE%" goto execute
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME% 1>&2
goto fail

:execute
set CLASSPATH=%APP_HOME%\gradle\wrapper\gradle-wrapper.jar
"%JAVA_EXE%" %JAVA_OPTS% %GRADLE_OPTS% "-Dorg.gradle.appname=%APP_BASE_NAME%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*
:end
@exit /b %ERRORLEVEL%
:fail
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% equ 0 set EXIT_CODE=1
exit /b %EXIT_CODE%
"""
    with open(os.path.join(project_dir, "gradlew.bat"), "w") as f: f.write(content)

def _write_gradlew_unix(project_dir):
    # Removed DEFAULT_JVM_OPTS that caused "could not find Xmx64m" errors in Linux/Codespace
    content = r"""#!/bin/sh
APP_BASE_NAME=$(basename "$0")
APP_HOME=$( cd "$( dirname "$0" )" > /dev/null && pwd )

if [ -n "$JAVA_HOME" ] ; then
    JAVACMD="$JAVA_HOME/bin/java"
else
    JAVACMD="java"
fi

CLASSPATH="$APP_HOME/gradle/wrapper/gradle-wrapper.jar"
exec "$JAVACMD" $JAVA_OPTS $GRADLE_OPTS "-Dorg.gradle.appname=$APP_BASE_NAME" -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
"""
    path = os.path.join(project_dir, "gradlew")
    with open(path, "w") as f: f.write(content)
    try: os.chmod(path, 0o755)
    except Exception: pass

# =================================================================
# UI & CONFIG
# =================================================================

class LoadingSpinner:
    def __init__(self, message="Processing"): self.message = message; self.running = False; self._thread = None
    def _spin(self):
        chars = ["|", "/", "-", "\\"]; idx = 0
        while self.running: sys.stdout.write(f"\r {C_CYAN}{chars[idx]}{C_RESET} {self.message}..."); sys.stdout.flush(); idx = (idx + 1) % len(chars); time.sleep(0.1)
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r"); sys.stdout.flush()
    def start(self): self.running = True; self._thread = threading.Thread(target=self._spin, daemon=True); self._thread.start()
    def stop(self): self.running = False; if self._thread: self._thread.join()

def clear_screen(): os.system("cls" if IS_WINDOWS else "clear")
def print_header():
    clear_screen()
    print(f"{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}| {C_CYAN}{C_BOLD}       MC FABRIC MOD ARCHITECT - BULLETPROOF ENGINE            {C_MAGENTA}{C_BOLD}|{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")

def print_card(title, lines, color=C_MAGENTA):
    print(f"{color}+- {C_WHITE}{C_BOLD}{title}{C_RESET}{color} " + "-" * (63 - len(title) - 3) + f"{C_RESET}")
    for line in lines: print(f"{color}|{C_RESET} {line}")
    print(f"{color}+" + "-" * 66 + f"{C_RESET}")

def load_config():
    defaults = {"default_out_base": "", "last_mc_version": "1.21.4", "java_home": "", "environment": "1"}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f: loaded = json.load(f)
            defaults.update(loaded)
        except Exception: pass
    return defaults

def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(config, f, indent=4)
    except Exception: pass

# =================================================================
# COMPILER
# =================================================================

def execute_build(project_dir, config, version_info=None, mod_id=None, mc_version=None):
    print(f"\n{C_MAGENTA}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_CYAN}{C_BOLD}           COMPILER ENGINE: EXECUTING FABRIC MOD BUILD              {C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}===================================================================={C_RESET}\n")
    original_cwd = os.getcwd()
    is_codespace = _last_session.get("is_codespace", False)
    if version_info and mod_id and mc_version: ensure_build_files(project_dir, mod_id, version_info, mc_version, is_codespace)
    gradle_version = version_info.get("gradle", "8.10") if version_info else "8.10"
    setup_gradle_wrapper(project_dir, config, gradle_version)
    os.chdir(project_dir)
    success = False; log_acc = []; env = get_subprocess_env(config)
    gradle_cmd = resolve_gradle_command(config, project_dir)
    cmd = [gradle_cmd, "clean", "build"]
    print(f"{C_CYAN}[i] Launching {os.path.basename(gradle_cmd)}...{C_RESET}\n")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break
            if line: sys.stdout.write(line); sys.stdout.flush(); log_acc.append(line)
        proc.communicate()
        if proc.returncode == 0: success = True
    except Exception as e: print(f"{C_RED}[X] Crash: {e}{C_RESET}"); log_acc.append(str(e))
    build_log = "".join(log_acc)
    if success:
        jar_files = []
        libs_dir = os.path.join(project_dir, "build", "libs")
        if os.path.exists(libs_dir): jar_files = [j for j in glob.glob(os.path.join(libs_dir, "*.jar")) if not any(x in os.path.basename(j).lower() for x in ["sources", "javadoc", "all"])]
        out = [f"{C_GREEN}{C_BOLD}Build Successful!{C_RESET}"]
        if jar_files: out.append(f"JAR: {C_GREEN}{os.path.basename(jar_files[0])}{C_RESET}")
        print_card("BUILD SUMMARY", out, C_GREEN)
    else: print_card("BUILD FAILURE", [f"{C_RED}Build failed.{C_RESET}"], C_RED)
    os.chdir(original_cwd)
    return success, build_log

def extract_failed_symbols(build_log):
    failed = []
    for line in build_log.splitlines():
        ll = line.lower()
        if "cannot find symbol" in ll: failed.append("CANNOT_FIND_SYMBOL")
        if "symbol:   method" in ll: failed.append(f"METHOD_NOT_FOUND:{line.split('method')[1].strip()}")
        if "symbol:   class" in ll: failed.append(f"CLASS_NOT_FOUND:{line.split('class')[1].strip()}")
    return failed

def run_healing_loop(project_dir, system_instruction, max_tokens, mc_version, config, mod_id, mod_class_name, pkg, expected_main_path, version_info, start_attempt=1, max_attempts=3):
    build_success, build_log = False, ""
    if start_attempt > 1:
        build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)
        if build_success: return True, build_log
    heal_attempts = start_attempt - 1
    while heal_attempts < start_attempt - 1 + max_attempts:
        heal_attempts += 1
        print(f"\n{C_YELLOW}[!] SELF-HEAL: Attempt {heal_attempts}...{C_RESET}")
        ext_log = capture_extended_errors(project_dir, config, version_info, mod_id, mc_version)
        combined_log = build_log + "\n\n--- EXTENDED ---\n" + ext_log
        workspace = ""
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith((".java", ".json")):
                    try:
                        with open(os.path.join(root, file), "r", encoding="utf-8") as f: rel = os.path.relpath(os.path.join(root, file), project_dir); workspace += f"\n\n================ FILE: {rel} ================\n{f.read()}\n================ END ================\n"
                    except Exception: pass
        vac = generate_fabric_version_constraints(mc_version, version_info)
        heal_prompt = f"CRITICAL COMPILATION FAILURE!\nFix for Fabric MC {mc_version}.\n\n--- COMPILER DIAGNOSTICS ---\n{combined_log}\n\n--- WORKSPACE CODE ---\n{workspace}\n\n{vac}\n\nDO NOT modify build files. ONLY output Java/resource files."
        heal_system = system_instruction + "\n\nSELF-HEAL Mode. ONLY output files that need changes."
        raw_text = execute_browser_request(heal_system, heal_prompt, project_dir, is_heal=True)
        heal_files = parse_ai_response(raw_text, expected_main_path, pkg, mod_class_name, mod_id)
        if heal_files:
            for key in list(heal_files.keys()):
                if key in ("build.gradle", "settings.gradle", "gradle.properties"): del heal_files[key]
            if heal_files:
                for rfp, code in heal_files.items():
                    fop = os.path.join(project_dir, os.path.normpath(rfp).replace("..", "").lstrip(os.sep))
                    os.makedirs(os.path.dirname(fop), exist_ok=True)
                    with open(fop, "w", encoding="utf-8") as f: f.write(code)
                run_precompilation_fixes(project_dir, mod_id, mod_id, pkg, mod_class_name, mc_version, version_info)
                build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)
                if build_success: break
    return build_success, build_log

def capture_extended_errors(project_dir, config, version_info=None, mod_id=None, mc_version=None):
    env = get_subprocess_env(config); original_cwd = os.getcwd()
    if version_info and mod_id and mc_version: ensure_build_files(project_dir, mod_id, version_info, mc_version, _last_session.get("is_codespace", False))
    os.chdir(project_dir)
    try:
        cmd = [resolve_gradle_command(config, project_dir), "clean", "build", "--stacktrace"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, timeout=180)
        return res.stdout
    except Exception as e: return str(e)
    finally: os.chdir(SCRIPT_DIR)

# =================================================================
# TEMPLATE GENERATORS
# =================================================================

def generate_build_gradle(pkg, mod_id, version_info, mc_version):
    loom = version_info.get("loom", "1.7.4"); java_ver = version_info.get("java", 21)
    return f"""plugins {{ id 'fabric-loom' version '{loom}'; id 'maven-publish' }}
version = project.mod_version; group = project.maven_group; base {{ archivesName = project.archives_base_name }}
repositories {{}}
dependencies {{ minecraft "com.mojang:minecraft:${{project.minecraft_version}}"; mappings "net.fabricmc:yarn:${{project.yarn_mappings}}:v2"; modImplementation "net.fabricmc:fabric-loader:${{project.loader_version}}"; modImplementation "net.fabricmc.fabric-api:fabric-api:${{project.fabric_version}}" }}
processResources {{ inputs.property "version", project.version; filesMatching("fabric.mod.json") {{ expand "version": project.version }} }}
tasks.withType(JavaCompile).configureEach {{ it.options.release = {java_ver} }}
java {{ sourceCompatibility = JavaVersion.VERSION_{java_ver}; targetCompatibility = JavaVersion.VERSION_{java_ver}; withSourcesJar() }}
publishing {{ publications {{ mavenJava(MavenPublication) {{ from components.java }} }} }}
"""

def generate_settings_gradle():
    return "pluginManagement { repositories { maven { name = 'Fabric'; url = 'https://maven.fabricmc.net/' }; gradlePluginPortal() } }\n"

def generate_gradle_properties(mc_version, version_info, is_codespace=False):
    loader = version_info.get("loader", "0.16.9"); yarn = version_info.get("yarn", f"{mc_version}+build.1"); fabric_api = version_info.get("fabric_api", f"0.100.0+{mc_version}")
    
    if is_codespace:
        # Optimized for GitHub Codespace (2GB-4GB RAM limit)
        jvm_args = "-Xmx1G -Xms512m -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=4M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1"
        parallel = "true"
        caching = "true"
    else:
        # PC Mode (Standard)
        jvm_args = "-Xmx2G"
        parallel = "false"
        caching = "true"

    return f"""org.gradle.jvmargs={jvm_args}
org.gradle.parallel={parallel}
org.gradle.caching={caching}

minecraft_version={mc_version}
yarn_mappings={yarn}
loader_version={loader}
mod_version=1.0.0
maven_group=com.example
archives_base_name=fabric-mod
fabric_version={fabric_api}
"""

def generate_fabric_mod_json(mod_id, mod_name, pkg, mod_class_name, mc_version, version_info):
    java_ver = version_info.get("java", 21)
    return json.dumps({"schemaVersion": 1, "id": mod_id, "version": "${version}", "name": mod_name, "description": f"A Fabric mod for Minecraft {mc_version}", "authors": ["Author"], "license": "MIT", "environment": "*", "entrypoints": {"main": [f"{pkg}.{mod_class_name}"], "client": []}, "mixins": [f"{mod_id}.mixins.json"], "depends": {"fabricloader": ">=0.15.0", "minecraft": f"~{mc_version}", "java": f">={java_ver}", "fabric-api": "*"}}, indent=2)

def generate_mixin_json(mod_id, pkg, version_info):
    java_ver = version_info.get("java", 21)
    return json.dumps({"required": True, "package": f"{pkg}.mixin", "compatibilityLevel": f"JAVA_{java_ver}", "minVersion": "0.8", "client": [], "mixins": [], "injectors": {"defaultRequire": 1}}, indent=2)

def generate_main_class(pkg, mod_class_name, mc_version, version_info):
    mod_id = mod_class_name.replace("Mod", "").lower()
    return f"""package {pkg};
import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
public class {mod_class_name} implements ModInitializer {{
    public static final String MOD_ID = "{mod_id}";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    @Override
    public void onInitialize() {{ LOGGER.info("Hello Fabric world!"); }}
}}
"""

def ensure_build_files(project_dir, mod_id, version_info, mc_version, is_codespace=False):
    fixes = []
    with open(os.path.join(project_dir, "build.gradle"), "w", encoding="utf-8") as f: f.write(generate_build_gradle("com.example", mod_id, version_info, mc_version)); fixes.append("Force-wrote build.gradle")
    with open(os.path.join(project_dir, "settings.gradle"), "w", encoding="utf-8") as f: f.write(generate_settings_gradle()); fixes.append("Force-wrote settings.gradle")
    with open(os.path.join(project_dir, "gradle.properties"), "w", encoding="utf-8") as f: f.write(generate_gradle_properties(mc_version, version_info, is_codespace)); fixes.append(f"Force-wrote gradle.properties ({'Codespace' if is_codespace else 'PC'} Memory)")
    return fixes

def _capitalize(s): return "".join(word.capitalize() for word in re.split(r'[_\-\s]+', s) if word)

# =================================================================
# MAIN PIPELINE
# =================================================================

def run_pipeline():
    try:
        print_header()
        config = load_config()

        # --- ENVIRONMENT SELECTION ---
        print(f"\n{C_WHITE}{C_BOLD}Select Environment:{C_RESET}")
        print(f" [{C_CYAN}1{C_RESET}] {C_GREEN}PC (Windows/Linux/Mac){C_RESET}")
        print(f" [{C_CYAN}2{C_RESET}] {C_MAGENTA}GitHub Codespace (Low RAM Optimization){C_RESET}")
        env_choice = input(f"Choice [Last: {config.get('environment', '1')}]: ").strip() or config.get('environment', '1')
        
        is_codespace = env_choice == "2"
        config["environment"] = env_choice
        save_config(config)
        _last_session["is_codespace"] = is_codespace

        if is_codespace:
            default_base = "./mods"
            env_tag = f"{C_MAGENTA}GitHub Codespace (Optimized){C_RESET}"
        else:
            default_base = "D:\\fabric_mods" if IS_WINDOWS else os.path.expanduser("~/fabric_mods")
            env_tag = f"{C_GREEN}PC Mode{C_RESET}"
        
        config["default_out_base"] = default_base

        # Diagnostics
        java_s = f"{C_RED}Missing{C_RESET}"
        env = get_subprocess_env(config)
        try:
            res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, timeout=10)
            if res.returncode == 0 or "version" in res.stdout.lower(): java_s = f"{C_GREEN}Available{C_RESET}"
        except Exception: pass
        
        print_card("ENVIRONMENT", [f"Mode: {env_tag}", f"Java: {java_s}", f"Storage: {C_CYAN}{default_base}{C_RESET}"], C_CYAN)

        # --- MODE SELECTION ---
        print(f"\n{C_WHITE}{C_BOLD}Select Operation:{C_RESET}")
        print(f" [{C_CYAN}1{C_RESET}] Create NEW Fabric Mod")
        print(f" [{C_CYAN}2{C_RESET}] EDIT Existing Mod")
        mode = input(f"{C_BOLD}Choice: {C_RESET}").strip()
        if mode not in ["1", "2"]: return None

        mc_version = input(f" MC Version [{config['last_mc_version']}]: ").strip() or config['last_mc_version']
        config["last_mc_version"] = mc_version; save_config(config)
        version_info = resolve_version_info(mc_version)

        print(f"\n{C_CYAN}--- Versions ---{C_RESET}")
        print(f"  Loom: {C_GREEN}{version_info.get('loom')}{C_RESET} | Gradle: {C_GREEN}{version_info.get('gradle')}{C_RESET} | Java: {C_GREEN}{version_info.get('java')}{C_RESET}")

        if mode == "2":
            project_dir = input(f"Path/name [{C_CYAN}{default_base}/modname{C_RESET}]: ").strip().replace('"', '').replace("'", "")
            if not os.path.isabs(project_dir): project_dir = os.path.abspath(os.path.join(default_base, project_dir))
            if not os.path.exists(project_dir): print(f"{C_RED}[X] Not found.{C_RESET}"); return None
            mod_name = os.path.basename(os.path.normpath(project_dir)); mod_id = mod_name.lower().replace(" ", "_")
            existing_context = ""
            for root, dirs, files in os.walk(project_dir):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                for file in files:
                    if file.endswith((".java", ".json")):
                        try:
                            with open(os.path.join(root, file), "r", encoding="utf-8") as f: rel = os.path.relpath(os.path.join(root, file), project_dir); existing_context += f"\n\n================ FILE: {rel} ================\n{f.read()}\n================ END ================\n"
                        except Exception: pass
            idea = input(f"\n{C_YELLOW}Changes/fixes?{C_RESET}\n-> ")
            extra = input("Extra: ").strip()
        else:
            mod_name = input("\nMod Name: ").strip()
            if not mod_name: return None
            mod_id = re.sub(r'[^a-z0-9_]', '_', mod_name.lower()).strip('_')
            custom_id = input(f" Mod ID [{C_CYAN}{mod_id}{C_RESET}]: ").strip()
            if custom_id: mod_id = re.sub(r'[^a-z0-9_]', '_', custom_id.lower()).strip('_')
            ub = input(f" Destination [{C_CYAN}{default_base}{C_RESET}]: ").strip().replace('"', '').replace("'", "") or default_base
            project_dir = os.path.abspath(os.path.join(ub, mod_id))
            os.makedirs(project_dir, exist_ok=True)
            idea = input("What should the mod do?\n-> "); extra = input("Extra: ").strip()

        pkg = f"com.example.{mod_id.replace('_', '')}"
        custom_pkg = input(f" Package [{C_CYAN}{pkg}{C_RESET}]: ").strip()
        if custom_pkg: pkg = custom_pkg
        mod_class_name = f"{_capitalize(mod_id)}Mod"
        custom_class = input(f" Main Class [{C_CYAN}{mod_class_name}{C_RESET}]: ").strip()
        if custom_class: mod_class_name = custom_class
        expected_main_path = f"src/main/java/{pkg.replace('.', '/')}/{mod_class_name}.java"

        vac = generate_fabric_version_constraints(mc_version, version_info)
        fmj_content = generate_fabric_mod_json(mod_id, mod_name, pkg, mod_class_name, mc_version, version_info)
        mixin_content = generate_mixin_json(mod_id, pkg, version_info)
        main_content = generate_main_class(pkg, mod_class_name, mc_version, version_info)
        build_content = generate_build_gradle(pkg, mod_id, version_info, mc_version)
        settings_content = generate_settings_gradle()
        props_content = generate_gradle_properties(mc_version, version_info, is_codespace)

        template_block = (
            f"================ FILE: src/main/resources/fabric.mod.json ================\n{fmj_content}\n================ END ================\n\n"
            f"================ FILE: src/main/resources/{mod_id}.mixins.json ================\n{mixin_content}\n================ END ================\n\n"
            f"================ FILE: {expected_main_path} ================\n{main_content}\n================ END ================\n"
        )

        si = (
            f"You are an Elite Minecraft Fabric Mod Architect writing production-grade mods.\n"
            f"Target: Fabric MC v{mc_version} using Gradle + Fabric Loom {version_info.get('loom')}. Java {version_info.get('java', 21)}.\n\n"
            f"{HARDCODED_FABRIC_MISTAKES}\n{vac}\n\n"
            f"FILES RULE: Generate ALL files including fabric.mod.json, mixin JSON, AND main mod class.\n"
            f"Main class '{mod_class_name}' at '{expected_main_path}'. Package: '{pkg}'. Mod ID: '{mod_id}'.\n\n"
            f"DO NOT generate build.gradle, settings.gradle, or gradle.properties.\n\n"
            f"FORMAT: Output files inside ================ FILE: path ================ blocks:\n\n{template_block}\n\n"
            f"NEVER import net.minecraft.client.* in server/common code. ALWAYS use Yarn mappings.\n"
        )

        pt = (f"Build Fabric mod for MC {mc_version}.\nName: '{mod_name}' | ID: '{mod_id}' | Pkg: '{pkg}' | Function: {idea} | Extra: {extra}\n"
              f"DO NOT modify build files.") if mode != "2" else (
            f"Edit '{mod_name}' for MC {mc_version}.\nFiles:\n{existing_context}\n\nChanges: {idea} | Extra: {extra}\nDO NOT modify build files.")

        raw_text = execute_browser_request(si, pt, project_dir)
        ftw = parse_ai_response(raw_text, expected_main_path, pkg, mod_class_name, mod_id)
        if not ftw: print(f"{C_RED}[X] No files found.{C_RESET}"); return project_dir

        for key in list(ftw.keys()):
            if key in ("build.gradle", "settings.gradle", "gradle.properties"): del ftw[key]
        if not any("fabric.mod.json" in f for f in ftw): ftw["src/main/resources/fabric.mod.json"] = fmj_content
        if not any(f"{mod_id}.mixins.json" in f for f in ftw): ftw[f"src/main/resources/{mod_id}.mixins.json"] = mixin_content

        if mode == "1" and any(k.strip().startswith("src") for k in ftw.keys()):
            sp = os.path.join(project_dir, "src")
            if os.path.exists(sp): shutil.rmtree(sp, ignore_errors=True)

        for rfp, code in ftw.items():
            fop = os.path.join(project_dir, os.path.normpath(rfp).replace("..", "").lstrip(os.sep))
            os.makedirs(os.path.dirname(fop), exist_ok=True)
            with open(fop, "w", encoding="utf-8") as f: f.write(code)
            print(f"  -> {C_CYAN}Synced:{C_RESET} {rfp}")

        run_precompilation_fixes(project_dir, mod_id, mod_name, pkg, mod_class_name, mc_version, version_info)
        print(f"\n{C_GREEN}[OK] Compiling...{C_RESET}")
        build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)

        _last_session.update({"system_instruction": si, "mc_version": mc_version, "config": config, "mod_id": mod_id, "mod_class_name": mod_class_name, "pkg": pkg, "expected_main_path": expected_main_path, "version_info": version_info, "heal_attempt_count": 0, "previous_errors": [], "build_failed": not build_success})

        if not build_success:
            build_success, build_log = run_healing_loop(project_dir, si, 65536, mc_version, config, mod_id, mod_class_name, pkg, expected_main_path, version_info, start_attempt=1, max_attempts=3)
        
        _last_session["build_failed"] = not build_success
        return project_dir
    except Exception as e:
        print(f"\n{C_RED}[X] Pipeline error: {e}{C_RESET}"); return None

def main():
    current_project_dir = None
    while True:
        try:
            result = run_pipeline()
            if result and os.path.exists(result): current_project_dir = result
        except Exception as e: print(f"\n{C_RED}[X] Crash: {e}{C_RESET}")
        
        print(f"\n{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")
        print(f" [{C_CYAN}1{C_RESET}] Create NEW Mod  [{C_CYAN}2{C_RESET}] Edit  [{C_CYAN}3{C_RESET}] Rebuild  [{C_CYAN}4{C_RESET}] Exit")
        choice = input(f"Select: {C_RESET}").strip()
        if choice == "4": sys.exit(0)
        # Simplified loop, just restart the script for new/edit/rebuild
        if choice in ["1", "2"]: continue
        if choice == "3":
            config = load_config(); is_codespace = config.get("environment", "1") == "2"
            base = "./mods" if is_codespace else ("D:\\fabric_mods" if IS_WINDOWS else "~/fabric_mods")
            tp = input(f"Path [{C_CYAN}{base}{C_RESET}]: ").strip()
            if not tp: tp = os.path.join(base, input("Folder: ").strip())
            elif not os.path.isabs(tp): tp = os.path.join(base, tp)
            if os.path.exists(tp): execute_build(os.path.abspath(tp), config)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print(f"\n{C_YELLOW}[!] Interrupted.{C_RESET}"); sys.exit(0)
