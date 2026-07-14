#!/usr/bin/env python3
"""
MC Fabric Mod Architect — Automatic Fabric Mod Maker
Browser-only mode. No API keys needed. Self-healing.
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
IS_PC_MODE = IS_WINDOWS
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

if IS_PC_MODE:
    DEFAULT_MAIN_STORAGE = "D:\\fabric_mods"
else:
    DEFAULT_MAIN_STORAGE = "/sdcard/Download/fabric_mods/mods"

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

EXCLUDED_DIRS = {".git", ".gradle", ".idea", "target", "build", "gradle", "out", "bin", ".loom"}

_last_session = {
    "provider": None, "model": None, "api_key": None,
    "system_instruction": None, "max_tokens": None,
    "mc_version": None, "build_tool": "Gradle",
    "project_dir": None, "build_failed": False,
    "config": None, "heal_attempt_count": 0,
    "previous_errors": [], "mod_id": None,
    "mod_class_name": None, "pkg": None,
    "expected_main_path": None, "java_version": None,
    "version_info": None,
}

# =================================================================
# FABRIC VERSION DATABASE — PINNED STABLE RELEASES
# Loom versions are PINNED to releases compatible with the
# corresponding Gradle version. NEVER auto-upgrade Loom.
# =================================================================

FABRIC_VERSION_DB = {
    "1.21.4": {
        "loader": "0.16.9",
        "yarn": "1.21.4+build.1",
        "fabric_api": "0.112.2+1.21.4",
        "loom": "1.7.4",
        "gradle": "8.10",
        "java": 21,
        "data_components": True,
        "identifier_of": True,
        "registries_class": True,
    },
    "1.21.3": {
        "loader": "0.16.7",
        "yarn": "1.21.3+build.2",
        "fabric_api": "0.106.0+1.21.3",
        "loom": "1.7.4",
        "gradle": "8.10",
        "java": 21,
        "data_components": True,
        "identifier_of": True,
        "registries_class": True,
    },
    "1.21.1": {
        "loader": "0.16.5",
        "yarn": "1.21.1+build.3",
        "fabric_api": "0.105.0+1.21.1",
        "loom": "1.7.4",
        "gradle": "8.10",
        "java": 21,
        "data_components": True,
        "identifier_of": True,
        "registries_class": True,
    },
    "1.20.6": {
        "loader": "0.16.0",
        "yarn": "1.20.6+build.1",
        "fabric_api": "0.100.0+1.20.6",
        "loom": "1.6.12",
        "gradle": "8.7",
        "java": 21,
        "data_components": True,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.20.4": {
        "loader": "0.15.11",
        "yarn": "1.20.4+build.3",
        "fabric_api": "0.97.2+1.20.4",
        "loom": "1.5.12",
        "gradle": "8.5",
        "java": 17,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.20.1": {
        "loader": "0.15.11",
        "yarn": "1.20.1+build.10",
        "fabric_api": "0.92.2+1.20.1",
        "loom": "1.4.6",
        "gradle": "8.3",
        "java": 17,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.19.4": {
        "loader": "0.15.6",
        "yarn": "1.19.4+build.2",
        "fabric_api": "0.87.2+1.19.4",
        "loom": "1.3.9",
        "gradle": "8.2",
        "java": 17,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.19.2": {
        "loader": "0.15.6",
        "yarn": "1.19.2+build.28",
        "fabric_api": "0.76.0+1.19.2",
        "loom": "1.2.7",
        "gradle": "8.0",
        "java": 17,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.18.2": {
        "loader": "0.15.6",
        "yarn": "1.18.2+build.4",
        "fabric_api": "0.77.0+1.18.2",
        "loom": "1.0.18",
        "gradle": "7.6",
        "java": 17,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
    "1.17.1": {
        "loader": "0.15.6",
        "yarn": "1.17.1+build.65",
        "fabric_api": "0.46.0+1.17",
        "loom": "0.12.46",
        "gradle": "7.4",
        "java": 16,
        "data_components": False,
        "identifier_of": False,
        "registries_class": False,
    },
}


def resolve_version_info(mc_version):
    info = FABRIC_VERSION_DB.get(mc_version)
    if info:
        return info.copy()
    inferred = _infer_version_defaults(mc_version)
    # Only fetch Loader/Yarn/API — NEVER auto-fetch Loom version
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
        if len(parts) >= 2:
            vf = float(f"{parts[0]}.{parts[1]}")
    except ValueError:
        pass
    java = 21 if vf >= 1.205 else (17 if vf >= 1.17 else 16)
    # Default to safe Loom/Gradle pair
    return {
        "loader": "0.16.9", "yarn": f"{mc_version}+build.1",
        "fabric_api": f"0.100.0+{mc_version}",
        "loom": "1.7.4", "gradle": "8.10",
        "java": java, "data_components": vf >= 1.205,
        "identifier_of": vf >= 1.212, "registries_class": vf >= 1.212,
    }


def _fetch_fabric_versions(mc_version):
    """Fetch Loader, Yarn, Fabric API versions from Fabric Meta.
    NEVER fetches Loom — that must stay pinned."""
    result = {}
    try:
        res = requests.get(
            f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}", timeout=10)
        if res.status_code == 200 and res.json():
            result["loader"] = res.json()[0]["loader"]["version"]
    except Exception:
        pass
    try:
        import xml.etree.ElementTree as ET
        res = requests.get(
            "https://maven.fabricmc.net/net/fabricmc/yarn/maven-metadata.xml", timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            versions = [v.text for v in root.findall(".//version")]
            matching = [v for v in versions if v.startswith(mc_version)]
            if matching:
                result["yarn"] = matching[-1]
    except Exception:
        pass
    try:
        import xml.etree.ElementTree as ET
        res = requests.get(
            "https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/maven-metadata.xml",
            timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            versions = [v.text for v in root.findall(".//version")]
            matching = [v for v in versions if mc_version in v]
            if matching:
                result["fabric_api"] = matching[-1]
    except Exception:
        pass
    return result


# =================================================================
# FABRIC-SPECIFIC RULES
# =================================================================

HARDCODED_FABRIC_MISTAKES = (
    "MANDATORY FABRIC RULES — VIOLATING ANY CAUSES FAILURE:\n"
    "1. ModInitializer: MUST implement onInitialize(). NOT JavaPlugin.\n"
    "2. fabric.mod.json: MUST include schemaVersion, id, version, entrypoints, depends.\n"
    "3. 1.20.5+ (Data Components): ItemStack.getTag()/getOrCreateTag() REMOVED. Use Data Components.\n"
    "4. 1.21.2+ (Identifier): new Identifier() REMOVED. Use Identifier.of(\"modid\", \"path\").\n"
    "5. 1.21.2+ (Registries): Use Registries class (Registries.ITEM) NOT Registry.ITEM static fields.\n"
    "6. Item registration: Registry.register(Registries.ITEM, id, item) for 1.21.2+.\n"
    "7. Item.Settings: Use new Item.Settings(). NOT deprecated constructors.\n"
    "8. Mixin: @Mixin target MUST be fully qualified intermediary/mapped class name.\n"
    "9. Client-only code MUST be in client entrypoint class, NEVER in common/main.\n"
    "10. Fabric API modules: Use correct imports (fabric-item-api-v1, fabric-command-api-v2, etc.).\n"
    "11. Resource paths: assets/modid/ — modid MUST match fabric.mod.json id exactly.\n"
    "12. Lang file: assets/modid/lang/en_us.json — JSON format, NOT YAML.\n"
    "13. NEVER import net.minecraft.client.* in common/server code. Use client entrypoint.\n"
    "14. NEVER use Bukkit/Spigot/Paper APIs in Fabric mods.\n"
    "15. ALWAYS use Yarn mappings (not Mojmap names like getOrCreateTag).\n"
)


def generate_fabric_version_constraints(mc_version, version_info):
    c = [f"TARGET: Fabric MC v{mc_version}", f"Java {version_info['java']}", ""]
    if version_info.get("data_components"):
        c.append("- DATA COMPONENTS: ItemStack.getTag() DOES NOT EXIST. Use Data Components:")
        c.append("  ItemStack.getOrDefault(DataComponentTypes.CUSTOM_DATA, NbtComponent.DEFAULT)")
        c.append("  ItemStack.set(DataComponentTypes.CUSTOM_DATA, nbt)")
    else:
        c.append("- NBT: Use ItemStack.getTag()/getOrCreateTag() for custom item data.")
    if version_info.get("identifier_of"):
        c.append("- Identifier: Use Identifier.of(\"modid\", \"name\"). new Identifier() DOES NOT EXIST in 1.21.2+.")
    else:
        c.append("- Identifier: Use new Identifier(\"modid\", \"name\").")
    if version_info.get("registries_class"):
        c.append("- Registries: Use net.minecraft.registry.Registries (Registries.ITEM, Registries.BLOCK, etc.)")
        c.append("  Registration: Registry.register(Registries.ITEM, Identifier.of(...), item)")
    else:
        c.append("- Registries: Use Registry.ITEM, Registry.BLOCK static fields.")
        c.append("  Registration: Registry.register(Registry.ITEM, new Identifier(...), item)")
    c.append(f"- Yarn mappings version: {version_info.get('yarn', 'unknown')}")
    c.append(f"- Fabric API version: {version_info.get('fabric_api', 'unknown')}")
    return "\n".join(c)


# =================================================================
# AI RESPONSE PARSER
# =================================================================

def parse_ai_response(raw_text, expected_main_path=None, pkg_structure=None,
                      mod_class_name=None, mod_id=None):
    files_to_write = {}
    lines = raw_text.splitlines()
    current_file = None
    current_content = []
    for line in lines:
        ls = line.strip()
        if ls.startswith("================ FILE:") and ls.endswith("================"):
            current_file = ls.replace("================ FILE:", "").replace("================", "").strip()
            current_content = []
            continue
        if ls == "================ END ================":
            if current_file:
                files_to_write[current_file] = clean_markdown_block("\n".join(current_content))
                current_file = None
            continue
        if current_file is not None:
            current_content.append(line)

    if not files_to_write:
        current_block = None
        current_lang = None
        current_content = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") and current_block is None:
                current_lang = stripped[3:].strip().lower()
                current_content = []
                current_block = True
                continue
            if stripped == "```" and current_block is not None:
                code = clean_markdown_block("\n".join(current_content))
                fname = infer_filename(code, current_lang, expected_main_path,
                                       pkg_structure, mod_class_name, mod_id)
                if fname and code.strip():
                    files_to_write[fname] = code
                current_block = None
                current_lang = None
                current_content = []
                continue
            if current_block is not None:
                current_content.append(line)

    if not files_to_write:
        pending_fname = None
        in_code = False
        code_lines = []
        for line in lines:
            stripped = line.strip()
            fname_match = re.match(r'(?:(?://)\s*)?(?:File|file|FILE)[:\s]+(\S+)', stripped)
            if fname_match and not in_code:
                pending_fname = fname_match.group(1)
                continue
            if stripped.startswith("```"):
                if in_code:
                    code = clean_markdown_block("\n".join(code_lines))
                    if pending_fname and code.strip():
                        files_to_write[pending_fname] = code
                    elif code.strip():
                        fname = infer_filename(code, "", expected_main_path,
                                               pkg_structure, mod_class_name, mod_id)
                        if fname:
                            files_to_write[fname] = code
                    in_code = False
                    code_lines = []
                    pending_fname = None
                else:
                    in_code = True
                    code_lines = []
                continue
            if in_code:
                code_lines.append(line)

    if not files_to_write and expected_main_path and pkg_structure:
        java_blocks = re.findall(
            r'(package\s+' + re.escape(pkg_structure) + r'\s*;.*?)(?=package\s+' + re.escape(pkg_structure) + r'\s*;|$)',
            raw_text, re.DOTALL)
        for block in java_blocks:
            block = block.strip()
            if not block:
                continue
            block = clean_markdown_block(block)
            fname = infer_filename(block, "java", expected_main_path,
                                   pkg_structure, mod_class_name, mod_id)
            if fname and block.strip():
                files_to_write[fname] = block

    if not files_to_write:
        class_pattern = r'public\s+class\s+(\w+)'
        class_matches = list(re.finditer(class_pattern, raw_text))
        for i, match in enumerate(class_matches):
            class_name = match.group(1)
            start = match.start()
            end = class_matches[i + 1].start() if i + 1 < len(class_matches) else len(raw_text)
            code = raw_text[start:end].strip()
            code = clean_markdown_block(code)
            if not code:
                continue
            if class_name == mod_class_name:
                if expected_main_path:
                    files_to_write[expected_main_path] = code
            elif pkg_structure:
                path = f"src/main/java/{pkg_structure.replace('.', '/')}/{class_name}.java"
                files_to_write[path] = code

    if not any("fabric.mod.json" in f for f in files_to_write):
        json_pattern = r'(\{[\s\S]*?"schemaVersion"[\s\S]*?\})'
        for jm in re.findall(json_pattern, raw_text):
            if "entrypoints" in jm:
                files_to_write["src/main/resources/fabric.mod.json"] = clean_markdown_block(jm)
                break

    return files_to_write


def infer_filename(code, lang, expected_main_path=None, pkg_structure=None,
                   mod_class_name=None, mod_id=None):
    code_stripped = code.strip()
    if not code_stripped:
        return None
    if '"schemaVersion"' in code_stripped and '"entrypoints"' in code_stripped:
        return "src/main/resources/fabric.mod.json"
    if '"compatibilityLevel"' in code_stripped and '"mixins"' in code_stripped:
        if mod_id:
            return f"src/main/resources/{mod_id}.mixins.json"
    if "plugins {" in code_stripped and ("repositories" in code_stripped or "dependencies" in code_stripped):
        if "loom" in code_stripped.lower() or "fabric" in code_stripped.lower():
            return "build.gradle"
    if code_stripped.strip().startswith("org.gradle") or (
        "minecraft_version" in code_stripped and "loader_version" in code_stripped
        and "class " not in code_stripped):
        return "gradle.properties"
    if "pluginManagement" in code_stripped and "repositories" in code_stripped and "class " not in code_stripped:
        return "settings.gradle"
    if "package " in code_stripped:
        pkg_match = re.search(r'package\s+([\w.]+)\s*;', code_stripped)
        if pkg_match:
            pkg = pkg_match.group(1)
            cls_match = re.search(r'public\s+(?:class|interface|enum)\s+(\w+)', code_stripped)
            if cls_match:
                cls_name = cls_match.group(1)
                if "client" in pkg.split(".") and "Client" in cls_name:
                    return f"src/client/java/{pkg.replace('.', '/')}/{cls_name}.java"
                return f"src/main/java/{pkg.replace('.', '/')}/{cls_name}.java"
    if expected_main_path and mod_class_name:
        if f"class {mod_class_name}" in code_stripped:
            return expected_main_path
    lang_lower = (lang or "").lower()
    if lang_lower in ("java", "jsp"):
        if pkg_structure:
            cls_match = re.search(r'public\s+class\s+(\w+)', code_stripped)
            if cls_match:
                return f"src/main/java/{pkg_structure.replace('.', '/')}/{cls_match.group(1)}.java"
    elif lang_lower in ("gradle", "groovy"):
        return "build.gradle"
    elif lang_lower in ("json",):
        if "schemaVersion" in code_stripped:
            return "src/main/resources/fabric.mod.json"
        if mod_id:
            return f"src/main/resources/assets/{mod_id}/lang/en_us.json"
    elif lang_lower in ("properties",):
        return "gradle.properties"
    return None


def clean_markdown_block(content):
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        content = "\n".join(lines)
    if content.endswith("```"):
        lines = content.splitlines()
        if lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return content.strip()


# =================================================================
# PRE-COMPILATION AUTO-FIXES
# =================================================================

def auto_fix_identifier_usage(project_dir, version_info):
    if not version_info.get("identifier_of"):
        return []
    fixes = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith(".java"):
                continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if "new Identifier(" in content:
                    content = re.sub(r'new\s+Identifier\s*\(', 'Identifier.of(', content)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    fixes.append(f"Replaced new Identifier() with Identifier.of() in {file}")
            except Exception:
                pass
    return fixes


def auto_fix_registries_usage(project_dir, version_info):
    if not version_info.get("registries_class"):
        return []
    fixes = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith(".java"):
                continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                modified = False
                registry_fields = ["ITEM", "BLOCK", "ENCHANTMENT", "ENTITY_TYPE",
                                   "FLUID", "GAME_EVENT", "PARTICLE_TYPE", "POTION",
                                   "SOUND_EVENT", "STATUS_EFFECT", "BLOCK_ENTITY_TYPE"]
                for field in registry_fields:
                    old = f"Registry.{field}"
                    new = f"Registries.{field}"
                    if old in content:
                        content = content.replace(old, new)
                        modified = True
                if modified:
                    if "import net.minecraft.registry.Registries;" not in content:
                        if "import net.minecraft.util.registry.Registry;" in content:
                            content = content.replace(
                                "import net.minecraft.util.registry.Registry;",
                                "import net.minecraft.registry.Registries;\nimport net.minecraft.registry.Registry;")
                        else:
                            pkg_end = content.find(";", content.find("package "))
                            if pkg_end != -1:
                                insert_pos = content.find("\n", pkg_end) + 1
                                content = (content[:insert_pos] +
                                           "import net.minecraft.registry.Registries;\n" +
                                           content[insert_pos:])
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    fixes.append(f"Replaced Registry.* with Registries.* in {file}")
            except Exception:
                pass
    return fixes


def auto_fix_fabric_mod_json(project_dir, mod_id, mod_name, pkg, mod_class_name, mc_version, version_info):
    fmj_path = os.path.join(project_dir, "src", "main", "resources", "fabric.mod.json")
    if not os.path.exists(fmj_path):
        return None
    try:
        with open(fmj_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            fmj = json.loads(content)
        except json.JSONDecodeError:
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
            try:
                fmj = json.loads(content)
            except json.JSONDecodeError:
                return None
        modified = False
        if "schemaVersion" not in fmj:
            fmj["schemaVersion"] = 1; modified = True
        if "id" not in fmj or not fmj["id"]:
            fmj["id"] = mod_id; modified = True
        if "version" not in fmj or not fmj["version"]:
            fmj["version"] = "${version}"; modified = True
        if "name" not in fmj or not fmj["name"]:
            fmj["name"] = mod_name; modified = True
        if "entrypoints" not in fmj:
            fmj["entrypoints"] = {}; modified = True
        if "main" not in fmj["entrypoints"] or not fmj["entrypoints"]["main"]:
            fmj["entrypoints"]["main"] = [f"{pkg}.{mod_class_name}"]; modified = True
        elif isinstance(fmj["entrypoints"]["main"], list):
            main_entry = f"{pkg}.{mod_class_name}"
            if main_entry not in fmj["entrypoints"]["main"]:
                fmj["entrypoints"]["main"].append(main_entry); modified = True
        if "depends" not in fmj:
            fmj["depends"] = {}; modified = True
        java_ver = version_info.get("java", 21)
        if "java" not in fmj["depends"]:
            fmj["depends"]["java"] = f">={java_ver}"; modified = True
        if "fabricloader" not in fmj["depends"]:
            fmj["depends"]["fabricloader"] = ">=0.15.0"; modified = True
        if "minecraft" not in fmj["depends"]:
            fmj["depends"]["minecraft"] = f"~{mc_version}"; modified = True
        if modified:
            with open(fmj_path, "w", encoding="utf-8") as f:
                json.dump(fmj, f, indent=2)
            return fmj_path
    except Exception:
        pass
    return None


def auto_fix_mixin_json(project_dir, mod_id, version_info):
    mixin_path = os.path.join(project_dir, "src", "main", "resources", f"{mod_id}.mixins.json")
    if not os.path.exists(mixin_path):
        return None
    try:
        with open(mixin_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            mj = json.loads(content)
        except json.JSONDecodeError:
            return None
        java_ver = version_info.get("java", 21)
        expected_level = f"JAVA_{java_ver}"
        if mj.get("compatibilityLevel") != expected_level:
            mj["compatibilityLevel"] = expected_level
            with open(mixin_path, "w", encoding="utf-8") as f:
                json.dump(mj, f, indent=2)
            return mixin_path
    except Exception:
        pass
    return None


def auto_generate_lang_file(project_dir, mod_id):
    lang_dir = os.path.join(project_dir, "src", "main", "resources", "assets", mod_id, "lang")
    lang_path = os.path.join(lang_dir, "en_us.json")
    translations = {}
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith(".java"):
                continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                for match in re.finditer(r'"item\.' + re.escape(mod_id) + r'\.(\w+)"', content):
                    key = f"item.{mod_id}.{match.group(1)}"
                    if key not in translations:
                        translations[key] = match.group(1).replace("_", " ").title()
                for match in re.finditer(r'"block\.' + re.escape(mod_id) + r'\.(\w+)"', content):
                    key = f"block.{mod_id}.{match.group(1)}"
                    if key not in translations:
                        translations[key] = match.group(1).replace("_", " ").title()
            except Exception:
                pass
    if not translations:
        return None
    existing = {}
    if os.path.exists(lang_path):
        try:
            with open(lang_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(translations)
    os.makedirs(lang_dir, exist_ok=True)
    with open(lang_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    return lang_path


def ensure_build_files(project_dir, mod_id, version_info, mc_version):
    """ALWAYS force-write build.gradle, settings.gradle, gradle.properties
    with the PINNED Loom version before every build. This prevents
    AI or user edits from breaking the Loom/Gradle compatibility."""
    pkg = "com.example"  # placeholder, doesn't matter for build files

    build_content = generate_build_gradle(pkg, mod_id, version_info, mc_version)
    settings_content = generate_settings_gradle()
    props_content = generate_gradle_properties(mc_version, version_info)

    fixes = []

    # Write build.gradle
    bg_path = os.path.join(project_dir, "build.gradle")
    with open(bg_path, "w", encoding="utf-8") as f:
        f.write(build_content)
    fixes.append(f"Force-wrote build.gradle (Loom {version_info.get('loom')})")

    # Write settings.gradle
    sg_path = os.path.join(project_dir, "settings.gradle")
    with open(sg_path, "w", encoding="utf-8") as f:
        f.write(settings_content)
    fixes.append("Force-wrote settings.gradle")

    # Write gradle.properties
    gp_path = os.path.join(project_dir, "gradle.properties")
    with open(gp_path, "w", encoding="utf-8") as f:
        f.write(props_content)
    fixes.append("Force-wrote gradle.properties")

    return fixes


def run_precompilation_fixes(project_dir, mod_id, mod_name, pkg, mod_class_name,
                             mc_version, version_info):
    print(f"\n{C_CYAN}[i] Running Fabric pre-compilation auto-fixes...{C_RESET}")
    fixes = []
    # ALWAYS ensure build files are correct
    fixes.extend(ensure_build_files(project_dir, mod_id, version_info, mc_version))
    fixes.extend(auto_fix_identifier_usage(project_dir, version_info))
    fixes.extend(auto_fix_registries_usage(project_dir, version_info))
    fmj = auto_fix_fabric_mod_json(project_dir, mod_id, mod_name, pkg,
                                   mod_class_name, mc_version, version_info)
    if fmj:
        fixes.append("Fixed fabric.mod.json")
    mj = auto_fix_mixin_json(project_dir, mod_id, version_info)
    if mj:
        fixes.append("Fixed mixin JSON compatibility level")
    lang = auto_generate_lang_file(project_dir, mod_id)
    if lang:
        fixes.append("Auto-generated/updated lang file")
    for fix in fixes:
        print(f"  -> {C_YELLOW}Auto-Fix:{C_RESET} {fix}")


# =================================================================
# CLIPBOARD
# =================================================================

def copy_to_clipboard(text):
    try:
        if IS_WINDOWS:
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        elif platform.system() == 'Darwin':
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        else:
            try:
                process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
                return True
            except FileNotFoundError:
                process = subprocess.Popen(['xsel', '--clipboard', '--input'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
                return True
    except Exception:
        return False


# =================================================================
# BROWSER MODE
# =================================================================

def execute_browser_request(system_instruction, prompt_text, project_dir, is_heal=False):
    full_prompt = f"SYSTEM INSTRUCTIONS:\n{system_instruction}\n\nUSER REQUEST:\n{prompt_text}"
    clipboard_ok = copy_to_clipboard(full_prompt)
    prompt_path = os.path.join(project_dir, "prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(full_prompt)
    mode_label = "HEALING" if is_heal else "GENERATION"
    print(f"\n{C_GREEN}{C_BOLD}=== BROWSER MODE: {mode_label} ==={C_RESET}")
    if clipboard_ok:
        print(f"{C_GREEN}[OK] Prompt COPIED TO CLIPBOARD!{C_RESET}")
    else:
        print(f"{C_YELLOW}[!] Auto-copy failed. Use prompt.txt as backup.{C_RESET}")
    print(f"{C_CYAN}[i] Prompt saved to: {C_WHITE}{prompt_path}{C_RESET}")
    print(f"\n{C_WHITE}{C_BOLD}Steps:{C_RESET}")
    print(f"  1. Open browser -> any AI (ChatGPT, Claude, Gemini, etc.)")
    if clipboard_ok:
        print(f"  2. {C_GREEN}Ctrl+V{C_RESET} to paste the prompt")
    else:
        print(f"  2. Open {C_YELLOW}prompt.txt{C_RESET}, copy all, paste into AI")
    print(f"  3. Copy the {C_GREEN}ENTIRE response{C_RESET} from the AI")
    print(f"  4. Save it to: {C_YELLOW}{os.path.join(project_dir, 'response.txt')}{C_RESET}")
    print(f"  5. Press Enter here")
    while True:
        input(f"\n{C_BOLD}{C_CYAN}Press Enter after saving response.txt...{C_RESET}")
        response_path = os.path.join(project_dir, "response.txt")
        if not os.path.exists(response_path):
            print(f"{C_RED}[!] response.txt NOT FOUND in {project_dir}{C_RESET}")
            continue
        try:
            with open(response_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            if not raw_text.strip():
                print(f"{C_RED}[!] response.txt is empty!{C_RESET}")
                continue
            try:
                os.remove(response_path)
            except Exception:
                pass
            return raw_text
        except Exception as e:
            print(f"{C_RED}[!] Error reading: {e}{C_RESET}")
            continue


# =================================================================
# BUILD TOOLS — AUTO WRAPPER
# =================================================================

def auto_detect_tool_home(tool_name):
    if not IS_WINDOWS:
        return None
    if tool_name == "java":
        for r in ["D:\\Java", "D:\\fabric_mods", "D:\\",
                   "C:\\Program Files\\Java", "C:\\Program Files\\Eclipse Adoptium",
                   "C:\\Program Files\\Microsoft", "C:\\Program Files\\Zulu",
                   "C:\\Program Files\\AdoptOpenJDK", "C:\\Program Files"]:
            for kw in ["java", "jdk", "jre"]:
                res = _scan_root_for_tool(r, kw, "java.exe")
                if res:
                    return res
    return None


def _find_tool_in_dir(directory, exe_name):
    if not os.path.isdir(directory):
        return None
    exe_path = os.path.join(directory, "bin", exe_name)
    if os.path.isfile(exe_path):
        return directory
    return None


def _scan_root_for_tool(root_dir, keyword, exe_name):
    if not os.path.isdir(root_dir):
        return None
    direct = _find_tool_in_dir(os.path.join(root_dir, keyword), exe_name)
    if direct:
        return direct
    try:
        for d in sorted(os.listdir(root_dir), reverse=True):
            if keyword.lower() in d.lower():
                result = _find_tool_in_dir(os.path.join(root_dir, d), exe_name)
                if result:
                    return result
    except Exception:
        pass
    return None


def get_subprocess_env(config):
    env = os.environ.copy()
    extra = []
    java_home = config.get("java_home", "").strip()
    if java_home and os.path.isdir(java_home):
        env["JAVA_HOME"] = java_home
        bin_dir = os.path.join(java_home, "bin")
        if os.path.isdir(bin_dir):
            extra.append(bin_dir)
    if extra:
        env["PATH"] = os.pathsep.join(extra) + os.pathsep + env.get("PATH", "")
    return env


def resolve_gradle_command(config, project_dir=None):
    if project_dir:
        if IS_WINDOWS:
            g = os.path.join(project_dir, "gradlew.bat")
        else:
            g = os.path.join(project_dir, "gradlew")
        if os.path.isfile(g):
            if not IS_WINDOWS:
                try:
                    os.chmod(g, 0o755)
                except Exception:
                    pass
            return g
    if IS_WINDOWS:
        return os.path.join(project_dir or ".", "gradlew.bat")
    else:
        return os.path.join(project_dir or ".", "gradlew")


def setup_gradle_wrapper(project_dir, config, gradle_version="8.10"):
    gradlew = os.path.join(project_dir, "gradlew.bat" if IS_WINDOWS else "gradlew")
    wrapper_jar = os.path.join(project_dir, "gradle", "wrapper", "gradle-wrapper.jar")

    if os.path.isfile(gradlew) and os.path.isfile(wrapper_jar):
        return True

    wrapper_dir = os.path.join(project_dir, "gradle", "wrapper")
    os.makedirs(wrapper_dir, exist_ok=True)

    global_cache = os.path.join(os.path.expanduser("~"), ".fabric_architect_cache")
    os.makedirs(global_cache, exist_ok=True)
    cached_jar = os.path.join(global_cache, "gradle-wrapper.jar")

    props = os.path.join(wrapper_dir, "gradle-wrapper.properties")
    with open(props, "w") as f:
        f.write(
            f"distributionBase=GRADLE_USER_HOME\n"
            f"distributionPath=wrapper/dists\n"
            f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip\n"
            f"networkTimeout=10000\n"
            f"validateDistributionUrl=true\n"
            f"zipStoreBase=GRADLE_USER_HOME\n"
            f"zipStorePath=wrapper/dists\n"
        )

    if os.path.isfile(cached_jar) and os.path.getsize(cached_jar) > 10000:
        print(f"  {C_GREEN}[OK] Using cached gradle-wrapper.jar{C_RESET}")
        shutil.copy2(cached_jar, wrapper_jar)
    else:
        print(f"  {C_CYAN}[i] Downloading gradle-wrapper.jar (one-time)...{C_RESET}")
        jar_url = "https://raw.githubusercontent.com/gradle/gradle/master/gradle/wrapper/gradle-wrapper.jar"
        try:
            r = requests.get(jar_url, timeout=30)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(cached_jar, "wb") as f:
                    f.write(r.content)
                shutil.copy2(cached_jar, wrapper_jar)
                print(f"  {C_GREEN}[OK] Downloaded and cached for future mods{C_RESET}")
            else:
                _download_and_extract_wrapper_jar(wrapper_jar, gradle_version)
                if os.path.isfile(wrapper_jar):
                    shutil.copy2(wrapper_jar, cached_jar)
        except Exception:
            _download_and_extract_wrapper_jar(wrapper_jar, gradle_version)
            if os.path.isfile(wrapper_jar):
                shutil.copy2(wrapper_jar, cached_jar)

    _write_gradlew_bat(project_dir)
    _write_gradlew_unix(project_dir)

    if os.path.isfile(wrapper_jar):
        return True
    else:
        print(f"  {C_RED}[!] Could not setup wrapper. Check internet.{C_RESET}")
        return False


def _download_and_extract_wrapper_jar(wrapper_jar, gradle_version):
    zip_url = f"https://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip"
    try:
        print(f"  {C_CYAN}[i] Downloading Gradle {gradle_version}...{C_RESET}")
        r = requests.get(zip_url, timeout=120, stream=True)
        total = int(r.headers.get('content-length', 0))
        downloaded = 0
        chunks = []
        for chunk in r.iter_content(chunk_size=8192):
            chunks.append(chunk)
            downloaded += len(chunk)
            if total:
                pct = int(100 * downloaded / total)
                sys.stdout.write(f"\r  Downloading: {pct}% ")
                sys.stdout.flush()
        print()
        zip_data = b''.join(chunks)
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for name in zf.namelist():
                if name.endswith("gradle-wrapper.jar"):
                    with zf.open(name) as src, open(wrapper_jar, "wb") as dst:
                        dst.write(src.read())
                    print(f"  {C_GREEN}[OK] Extracted wrapper JAR{C_RESET}")
                    return
    except Exception as e:
        print(f"  {C_RED}[!] Fallback download failed: {e}{C_RESET}")


def _write_gradlew_bat(project_dir):
    content = r"""@rem
@if "%DEBUG%"=="" @echo off

set DIRNAME=%~dp0
if "%DIRNAME%"=="" set DIRNAME=.
set APP_BASE_NAME=%~n0
set APP_HOME=%DIRNAME%

for %%i in ("%APP_HOME%") do set APP_HOME=%%~fi

set DEFAULT_JVM_OPTS="-Xmx64m" "-Xms64m"

if defined JAVA_HOME goto findJavaFromJavaHome

set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if %ERRORLEVEL% equ 0 goto execute

echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH. 1>&2
goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe

if exist "%JAVA_EXE%" goto execute

echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME% 1>&2
goto fail

:execute

set CLASSPATH=%APP_HOME%\gradle\wrapper\gradle-wrapper.jar

"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% "-Dorg.gradle.appname=%APP_BASE_NAME%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*

:end
@exit /b %ERRORLEVEL%

:fail
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% equ 0 set EXIT_CODE=1
exit /b %EXIT_CODE%
"""
    with open(os.path.join(project_dir, "gradlew.bat"), "w") as f:
        f.write(content)


def _write_gradlew_unix(project_dir):
    content = r"""#!/bin/sh

APP_BASE_NAME=$(basename "$0")
APP_HOME=$( cd "$( dirname "$0" )" > /dev/null && pwd )

DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'

if [ -n "$JAVA_HOME" ] ; then
    JAVACMD="$JAVA_HOME/bin/java"
else
    JAVACMD="java"
fi

CLASSPATH="$APP_HOME/gradle/wrapper/gradle-wrapper.jar"

exec "$JAVACMD" $DEFAULT_JVM_OPTS $JAVA_OPTS $GRADLE_OPTS "-Dorg.gradle.appname=$APP_BASE_NAME" -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
"""
    path = os.path.join(project_dir, "gradlew")
    with open(path, "w") as f:
        f.write(content)
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass


def silent_auto_configure(config):
    if not IS_PC_MODE:
        return config
    home = config.get("java_home", "").strip()
    if not (home and os.path.isfile(os.path.join(home, "bin", "java.exe"))):
        det = auto_detect_tool_home("java")
        if det:
            config["java_home"] = det
            save_config(config)
    return config


def interactive_tool_setup(config):
    if not IS_PC_MODE:
        return config
    env = get_subprocess_env(config)
    java_ok = False
    try:
        res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=env, timeout=10)
        java_ok = res.returncode == 0 or "version" in res.stdout.lower()
    except Exception:
        pass
    if not java_ok:
        j = input(f"{C_YELLOW}[!] Java not found. Enter Java home [blank to skip]: {C_RESET}").strip()
        if j and os.path.isdir(j):
            java_exe = os.path.join(j, "bin", "java.exe" if IS_WINDOWS else "java")
            if os.path.isfile(java_exe):
                config["java_home"] = j
                save_config(config)
    return config


# =================================================================
# SPINNER & UI
# =================================================================

class LoadingSpinner:
    def __init__(self, message="Processing"):
        self.message = message
        self.running = False
        self._thread = None

    def _spin(self):
        chars = ["|", "/", "-", "\\"]
        idx = 0
        while self.running:
            sys.stdout.write(f"\r {C_CYAN}{chars[idx]}{C_RESET} {self.message}...")
            sys.stdout.flush()
            idx = (idx + 1) % len(chars)
            time.sleep(0.1)
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join()


def clear_screen():
    os.system("cls" if IS_WINDOWS else "clear")


def print_header():
    clear_screen()
    mode_label = f"{C_GREEN}PC MODE{C_RESET}" if IS_PC_MODE else f"{C_CYAN}MOBILE MODE{C_RESET}"
    print(f"{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}| {C_CYAN}{C_BOLD}       MC FABRIC MOD ARCHITECT - BULLETPROOF ENGINE            {C_MAGENTA}{C_BOLD}|{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}| {C_WHITE}            Environment: {mode_label}                        {C_MAGENTA}{C_BOLD}|{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")


def print_card(title, lines, color=C_MAGENTA):
    print(f"{color}+- {C_WHITE}{C_BOLD}{title}{C_RESET}{color} " + "-" * (63 - len(title) - 3) + f"{C_RESET}")
    for line in lines:
        print(f"{color}|{C_RESET} {line}")
    print(f"{color}+" + "-" * 66 + f"{C_RESET}")


# =================================================================
# CONFIG & DIAGNOSTICS
# =================================================================

def load_config():
    defaults = {
        "default_out_base": DEFAULT_MAIN_STORAGE,
        "last_mc_version": "1.21.4",
        "java_home": "",
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except Exception:
            pass
    return defaults


def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass


def perform_system_diagnostics(config):
    java_s = f"{C_RED}Missing{C_RESET}"
    env = get_subprocess_env(config)
    try:
        res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=env, timeout=10)
        if res.returncode == 0 or "version" in res.stdout.lower():
            for l in res.stdout.splitlines():
                if "version" in l.lower():
                    java_s = f"{C_GREEN}Available ({l.strip()}){C_RESET}"
                    break
            if "Missing" in java_s:
                java_s = f"{C_GREEN}Available{C_RESET}"
    except Exception:
        pass
    env_tag = "Windows/PC" if IS_PC_MODE else "Mobile/Termux"
    diag = [
        f"Environment   : {C_GREEN}{env_tag}{C_RESET}",
        f"Java Runtime  : {java_s}",
        f"Gradle Status : {C_CYAN}Auto-Wrapper (no install needed){C_RESET}",
        f"Default Base  : {C_GREEN}{config.get('default_out_base')}{C_RESET}",
    ]
    print_card("ENVIRONMENT DIAGNOSTICS", diag, C_CYAN)


# =================================================================
# COMPILER
# =================================================================

def execute_build(project_dir, config, version_info=None, mod_id=None, mc_version=None):
    print(f"\n{C_MAGENTA}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_CYAN}{C_BOLD}           COMPILER ENGINE: EXECUTING FABRIC MOD BUILD              {C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}===================================================================={C_RESET}\n")

    original_cwd = os.getcwd()

    # ALWAYS force-correct build files before compiling
    if version_info and mod_id and mc_version:
        ensure_build_files(project_dir, mod_id, version_info, mc_version)

    gradle_version = version_info.get("gradle", "8.10") if version_info else "8.10"
    setup_gradle_wrapper(project_dir, config, gradle_version)

    os.chdir(project_dir)
    success = False
    log_acc = []
    env = get_subprocess_env(config)
    gradle_cmd = resolve_gradle_command(config, project_dir)
    cmd = [gradle_cmd, "clean", "build"]
    print(f"{C_CYAN}[i] Launching {os.path.basename(gradle_cmd)}...{C_RESET}\n")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, env=env)
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                log_acc.append(line)
        proc.communicate()
        if proc.returncode == 0:
            success = True
    except FileNotFoundError:
        err = f"[X] gradlew not found at: {gradle_cmd}"
        print(f"{C_RED}{err}{C_RESET}")
        log_acc.append(err)
    except Exception as e:
        err = f"[X] Compilation crashed: {e}"
        print(f"{C_RED}{err}{C_RESET}")
        log_acc.append(err)

    build_log = "".join(log_acc)
    if success:
        jar_files = []
        libs_dir = os.path.join(project_dir, "build", "libs")
        if os.path.exists(libs_dir):
            jar_files = [j for j in glob.glob(os.path.join(libs_dir, "*.jar"))
                         if not any(x in os.path.basename(j).lower() for x in ["sources", "javadoc", "all"])]
        out = [f"{C_GREEN}{C_BOLD}Status: Build Successful!{C_RESET}",
               f"Project: {C_WHITE}{project_dir}{C_RESET}"]
        if jar_files:
            out.append(f"JAR File   : {C_GREEN}{os.path.basename(jar_files[0])}{C_RESET}")
        print_card("BUILD SUMMARY", out, C_GREEN)
    else:
        print_card("BUILD FAILURE",
                   [f"{C_RED}Build failed.{C_RESET}", "Review errors, then Edit or Continue Healing."], C_RED)
    os.chdir(original_cwd)
    return success, build_log


def capture_extended_errors(project_dir, config, version_info=None, mod_id=None, mc_version=None):
    env = get_subprocess_env(config)
    original_cwd = os.getcwd()

    if version_info and mod_id and mc_version:
        ensure_build_files(project_dir, mod_id, version_info, mc_version)

    os.chdir(project_dir)
    gradle_version = version_info.get("gradle", "8.10") if version_info else "8.10"
    setup_gradle_wrapper(project_dir, config, gradle_version)
    try:
        gradle_cmd = resolve_gradle_command(config, project_dir)
        cmd = [gradle_cmd, "clean", "build", "--stacktrace"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=env, timeout=180)
        return res.stdout
    except Exception as e:
        return f"Extended error capture failed: {e}"
    finally:
        os.chdir(SCRIPT_DIR)


# =================================================================
# EXTRACT ERRORS
# =================================================================

def extract_failed_symbols(build_log):
    failed = []
    for line in build_log.splitlines():
        ll = line.lower()
        if "cannot find symbol" in ll:
            failed.append("CANNOT_FIND_SYMBOL")
        if "symbol:   method" in ll:
            parts = line.split("method")
            if len(parts) >= 2:
                failed.append(f"METHOD_NOT_FOUND:{parts[1].strip().rstrip(')')}")
        if "symbol:   class" in ll:
            parts = line.split("class")
            if len(parts) >= 2:
                failed.append(f"CLASS_NOT_FOUND:{parts[1].strip()}")
        if "does not override abstract method" in ll or "is not abstract and does not override" in ll:
            failed.append(f"MISSING_ABSTRACT:{line.strip()}")
        if "incompatible types" in ll:
            failed.append(f"INCOMPATIBLE_TYPES:{line.strip()}")
        if "package does not exist" in ll:
            failed.append(f"PACKAGE_MISSING:{line.strip()}")
    return failed


# =================================================================
# HEALING ENGINE
# =================================================================

def run_healing_loop(project_dir, system_instruction, max_tokens, mc_version, config,
                     mod_id, mod_class_name, pkg, expected_main_path, version_info,
                     start_attempt=1, max_attempts=3):
    build_success = False
    build_log = ""
    if start_attempt > 1:
        print(f"\n{C_CYAN}[i] Running build to get current errors...{C_RESET}")
        build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)
        if build_success:
            return True, build_log

    heal_attempts = start_attempt - 1
    previous_errors = _last_session.get("previous_errors", [])

    while heal_attempts < start_attempt - 1 + max_attempts:
        heal_attempts += 1
        print(f"\n{C_YELLOW}{C_BOLD}[!] SELF-HEAL: Attempt {heal_attempts}...{C_RESET}")
        print(f"  {C_CYAN}[i] Capturing extended errors...{C_RESET}")
        ext_log = capture_extended_errors(project_dir, config, version_info, mod_id, mc_version)
        combined_log = build_log + "\n\n--- EXTENDED DETAILS ---\n" + ext_log

        workspace = ""
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith((".java", ".json", ".gradle", ".properties")):
                    try:
                        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                            rel = os.path.relpath(os.path.join(root, file), project_dir)
                            workspace += (f"\n\n================ FILE: {rel} "
                                          f"================\n{f.read()}\n"
                                          f"================ END ================\n")
                    except Exception:
                        pass

        failed_symbols = extract_failed_symbols(combined_log)
        symbol_warning = ""
        if failed_symbols:
            symbol_warning = "\n\nCOMPILER-CONFIRMED ERRORS:\n"
            for sym in failed_symbols:
                if "METHOD_NOT_FOUND:" in sym:
                    symbol_warning += (f"- METHOD '{sym.replace('METHOD_NOT_FOUND:', '')}' "
                                       f"DOES NOT EXIST for Fabric MC {mc_version}.\n")
                elif "CLASS_NOT_FOUND:" in sym:
                    symbol_warning += f"- CLASS '{sym.replace('CLASS_NOT_FOUND:', '')}' DOES NOT EXIST.\n"
                elif "PACKAGE_MISSING:" in sym:
                    symbol_warning += f"- {sym.split(':', 1)[1]}\n"
            symbol_warning += "These GENUINELY do not exist. Do NOT retry the same approach.\n"

        repeat_warning = ""
        current_errors = set(failed_symbols)
        overlap = current_errors.intersection(set(previous_errors))
        if overlap:
            repeat_warning = "\n\nREPEATED ERROR WARNING: USE A COMPLETELY DIFFERENT STRATEGY:\n"
            for err in overlap:
                repeat_warning += f"  - {err}\n"

        previous_errors = failed_symbols
        vac = generate_fabric_version_constraints(mc_version, version_info)

        strictness = ""
        if heal_attempts >= 2:
            strictness = f"\n\nSTRICTNESS ESCALATION: ONLY use methods 100% certain to exist for Fabric MC {mc_version}.\n"
        if heal_attempts >= 4:
            strictness += "\nNUCLEAR OPTION: REMOVE complex API usage. Working mod > broken mod.\n"

        heal_prompt = (f"CRITICAL COMPILATION FAILURE!\n"
                       f"Fix the build errors for Fabric MC {mc_version}.\n\n"
                       f"--- COMPILER DIAGNOSTICS ---\n{combined_log}\n"
                       f"---------------------------\n\n"
                       f"{symbol_warning}\n{repeat_warning}\n\n"
                       f"--- WORKSPACE CODE ---\n{workspace}\n"
                       f"----------------------\n\n{vac}\n\n"
                       f"TASK:\n1. Read errors CAREFULLY.\n"
                       f"2. Find CORRECT alternative for Fabric MC {mc_version} with Yarn mappings.\n"
                       f"3. Return files in ================ FILE: path ================ blocks.\n"
                       f"4. If using Registry: ensure correct class (Registry vs Registries).\n"
                       f"5. If using Identifier: ensure correct constructor (new vs .of()).\n"
                       f"6. If 1.20.5+: use Data Components, NOT NBT.\n"
                       f"7. DO NOT modify build.gradle, settings.gradle, or gradle.properties — they are correct.\n"
                       f"{strictness}")

        heal_system = (system_instruction + "\n\n"
                       "SELF-HEAL Mode. Compiler errors are FACTUAL. "
                       "Do NOT retry failed methods. "
                       "DO NOT modify build.gradle, settings.gradle, or gradle.properties — they are managed by the tool. "
                       "ONLY output Java source files and resource files that need changes.")

        raw_text = execute_browser_request(heal_system, heal_prompt, project_dir, is_heal=True)

        heal_files = parse_ai_response(raw_text, expected_main_path, pkg, mod_class_name, mod_id)
        if heal_files:
            # Remove any build files the AI might have tried to change
            for key in list(heal_files.keys()):
                if key in ("build.gradle", "settings.gradle", "gradle.properties"):
                    del heal_files[key]

            if not heal_files:
                print(f"\n{C_YELLOW}[!] AI only modified build files (which we manage). Skipping.{C_RESET}")
                continue

            for rfp, code in heal_files.items():
                crp = os.path.normpath(rfp).replace("..", "")
                if crp.startswith(os.sep):
                    crp = crp[1:]
                fop = os.path.join(project_dir, crp)
                os.makedirs(os.path.dirname(fop), exist_ok=True)
                with open(fop, "w", encoding="utf-8") as f:
                    f.write(code)
                print(f"  -> {C_GREEN}Healed:{C_RESET} {crp}")

            run_precompilation_fixes(project_dir, mod_id, mod_id, pkg,
                                     mod_class_name, mc_version, version_info)
            print(f"\n{C_GREEN}[OK] Patch applied. Compiling...{C_RESET}")
            build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)
            if build_success:
                print(f"\n{C_GREEN}{C_BOLD}[OK] HEALED on Attempt {heal_attempts}!{C_RESET}")
                _last_session.update({"heal_attempt_count": heal_attempts,
                                      "previous_errors": [], "build_failed": False})
                break
            else:
                _last_session.update({"heal_attempt_count": heal_attempts,
                                      "previous_errors": failed_symbols})
        else:
            print(f"\n{C_RED}[!] No file blocks found in AI response.{C_RESET}")

    if not build_success:
        _last_session.update({"build_failed": True, "previous_errors": previous_errors})
        print(f"\n{C_RED}{C_BOLD}[X] Still broken after {max_attempts} attempts.{C_RESET}")
    return build_success, build_log


# =================================================================
# POST-ACTION MENU
# =================================================================

def prompt_post_action_menu(current_project_dir=None):
    print(f"\n{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}|                      NEXT OPERATION HUB                          |{C_RESET}")
    print(f"{C_MAGENTA}{C_BOLD}+------------------------------------------------------------------+{C_RESET}")
    print(f" [{C_CYAN}1{C_RESET}] {C_WHITE}{C_BOLD}Create NEW Mod{C_RESET}")
    if current_project_dir and os.path.exists(current_project_dir):
        print(f" [{C_CYAN}2{C_RESET}] {C_WHITE}{C_BOLD}Edit this mod{C_RESET} ({os.path.basename(current_project_dir)})")
    else:
        print(f" [{C_CYAN}2{C_RESET}] {C_DARK_GRAY}Edit mod (no active project){C_RESET}")
    if _last_session.get("build_failed") and current_project_dir:
        last = _last_session.get("heal_attempt_count", 0)
        print(f" [{C_CYAN}3{C_RESET}] {C_YELLOW}{C_BOLD}Continue healing{C_RESET} (last: attempt {last})")
        print(f" [{C_CYAN}4{C_RESET}] {C_RED}{C_BOLD}Exit{C_RESET}")
        mx = 4
    else:
        print(f" [{C_CYAN}3{C_RESET}] REBUILD (Offline)")
        print(f" [{C_CYAN}4{C_RESET}] {C_RED}{C_BOLD}Exit{C_RESET}")
        mx = 4
    choice = input(f"\n{C_BOLD}Select (1-{mx}): {C_RESET}").strip()
    if choice == "1":
        return "new", None
    elif choice == "2" and current_project_dir:
        return "edit", current_project_dir
    elif choice == "3" and _last_session.get("build_failed") and current_project_dir:
        li = input(f" {C_YELLOW}How many additional healing loops? (1-20): {C_RESET}").strip()
        try:
            loops = max(1, min(20, int(li)))
        except ValueError:
            loops = 3
        return "heal", (current_project_dir, loops)
    elif choice == "3":
        config = load_config()
        default_base = config.get("default_out_base", DEFAULT_MAIN_STORAGE)
        tp = input(f" Path [{C_CYAN}{default_base}{C_RESET}]: ").strip().replace('"', '').replace("'", "")
        if not tp:
            tp = os.path.join(default_base, input("Folder name: ").strip())
        elif not os.path.isabs(tp):
            tp = os.path.join(default_base, tp)
        if os.path.exists(tp):
            execute_build(os.path.abspath(tp), config)
        return "rebuild", None
    else:
        print(f"\n{C_GREEN}[OK] Goodbye!{C_RESET}")
        sys.exit(0)


def continue_healing(project_dir, additional_loops):
    s = _last_session
    if not s.get("system_instruction"):
        print(f"{C_RED}[X] No previous session.{C_RESET}")
        return
    last = s.get("heal_attempt_count", 0)
    print(f"\n{C_CYAN}{C_BOLD}=== CONTINUE HEALING ==={C_RESET}")
    print(f"  Previous: {last} | Additional: {additional_loops} | Target: Fabric MC v{s['mc_version']}")
    version_info = s.get("version_info") or resolve_version_info(s["mc_version"])
    build_success, _ = run_healing_loop(
        project_dir, s["system_instruction"], s["max_tokens"], s["mc_version"], s["config"],
        s.get("mod_id", ""), s.get("mod_class_name", ""),
        s.get("pkg", ""), s.get("expected_main_path", ""),
        version_info, start_attempt=last + 1, max_attempts=additional_loops)
    if build_success:
        print(f"\n{C_GREEN}{C_BOLD}[OK] Healing successful!{C_RESET}")
    else:
        print(f"\n{C_RED}[X] Still failing. Select 'Continue healing' again for more.{C_RESET}")


# =================================================================
# TEMPLATE GENERATORS
# =================================================================

def generate_build_gradle(pkg, mod_id, version_info, mc_version):
    loom = version_info.get("loom", "1.7.4")
    java_ver = version_info.get("java", 21)
    return f"""plugins {{
    id 'fabric-loom' version '{loom}'
    id 'maven-publish'
}}

version = project.mod_version
group = project.maven_group

base {{
    archivesName = project.archives_base_name
}}

repositories {{
}}

dependencies {{
    minecraft "com.mojang:minecraft:${{project.minecraft_version}}"
    mappings "net.fabricmc:yarn:${{project.yarn_mappings}}:v2"
    modImplementation "net.fabricmc:fabric-loader:${{project.loader_version}}"
    modImplementation "net.fabricmc.fabric-api:fabric-api:${{project.fabric_version}}"
}}

processResources {{
    inputs.property "version", project.version
    filesMatching("fabric.mod.json") {{
        expand "version": project.version
    }}
}}

tasks.withType(JavaCompile).configureEach {{
    it.options.release = {java_ver}
}}

java {{
    sourceCompatibility = JavaVersion.VERSION_{java_ver}
    targetCompatibility = JavaVersion.VERSION_{java_ver}
    withSourcesJar()
}}

jar {{
    from("LICENSE") {{
        rename {{ "${{it}}_${{project.archivesBaseName}}" }}
    }}
}}

publishing {{
    publications {{
        mavenJava(MavenPublication) {{
            from components.java
        }}
    }}
}}
"""


def generate_settings_gradle():
    return """pluginManagement {
    repositories {
        maven {
            name = 'Fabric'
            url = 'https://maven.fabricmc.net/'
        }
        gradlePluginPortal()
    }
}
"""


def generate_gradle_properties(mc_version, version_info):
    loader = version_info.get("loader", "0.16.9")
    yarn = version_info.get("yarn", f"{mc_version}+build.1")
    fabric_api = version_info.get("fabric_api", f"0.100.0+{mc_version}")
    return f"""org.gradle.jvmargs=-Xmx2G

# Fabric Properties
minecraft_version={mc_version}
yarn_mappings={yarn}
loader_version={loader}

# Mod Properties
mod_version=1.0.0
maven_group=com.example
archives_base_name=fabric-mod

# Dependencies
fabric_version={fabric_api}
"""


def generate_fabric_mod_json(mod_id, mod_name, pkg, mod_class_name, mc_version, version_info):
    java_ver = version_info.get("java", 21)
    return json.dumps({
        "schemaVersion": 1,
        "id": mod_id,
        "version": "${version}",
        "name": mod_name,
        "description": f"A Fabric mod for Minecraft {mc_version}",
        "authors": ["Author"],
        "contact": {},
        "license": "MIT",
        "icon": f"assets/{mod_id}/icon.png",
        "environment": "*",
        "entrypoints": {"main": [f"{pkg}.{mod_class_name}"], "client": []},
        "mixins": [f"{mod_id}.mixins.json"],
        "depends": {
            "fabricloader": ">=0.15.0",
            "minecraft": f"~{mc_version}",
            "java": f">={java_ver}",
            "fabric-api": "*",
        },
    }, indent=2)


def generate_mixin_json(mod_id, pkg, version_info):
    java_ver = version_info.get("java", 21)
    return json.dumps({
        "required": True,
        "package": f"{pkg}.mixin",
        "compatibilityLevel": f"JAVA_{java_ver}",
        "minVersion": "0.8",
        "client": [],
        "mixins": [],
        "injectors": {"defaultRequire": 1},
    }, indent=2)


def generate_main_class(pkg, mod_class_name, mc_version, version_info):
    mod_id = _safe_mod_id_from_class(mod_class_name)
    return f"""package {pkg};

import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class {mod_class_name} implements ModInitializer {{
    public static final String MOD_ID = "{mod_id}";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitialize() {{
        LOGGER.info("Hello Fabric world!");
    }}
}}
"""


def _safe_mod_id_from_class(class_name):
    name = class_name
    for suffix in ["Mod", "Initializer"]:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[:-len(suffix)]
    return name.lower()


def _capitalize(s):
    return "".join(word.capitalize() for word in re.split(r'[_\-\s]+', s) if word)


# =================================================================
# CORE PIPELINE — BROWSER ONLY
# =================================================================

def run_pipeline(force_mode=None, force_path=None):
    try:
        print_header()
        config = load_config()
        config = silent_auto_configure(config)
        perform_system_diagnostics(config)

        if IS_PC_MODE:
            env = get_subprocess_env(config)
            java_ok = False
            try:
                res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, env=env, timeout=10)
                java_ok = res.returncode == 0 or "version" in res.stdout.lower()
            except Exception:
                pass
            if not java_ok:
                config = interactive_tool_setup(config)
                print(f"\n{C_CYAN}[i] Re-checking...{C_RESET}")
                perform_system_diagnostics(config)

        if force_mode:
            mode = force_mode
        else:
            print(f"\n{C_WHITE}{C_BOLD}Select Operation:{C_RESET}")
            print(f" [{C_CYAN}1{C_RESET}] Create NEW Fabric Mod")
            print(f" [{C_CYAN}2{C_RESET}] EDIT Existing Fabric Mod")
            mode = input(f"{C_BOLD}Choice: {C_RESET}").strip()
        if mode not in ["1", "2"]:
            print(f"{C_RED}[X] Invalid.{C_RESET}")
            return None

        default_base = config.get("default_out_base", DEFAULT_MAIN_STORAGE)

        print(f"\n{C_WHITE}{C_BOLD}Project Config:{C_RESET}")
        mc_version = input(f" MC Version [{config['last_mc_version']}]: ").strip() or config['last_mc_version']
        config["last_mc_version"] = mc_version
        save_config(config)

        version_info = resolve_version_info(mc_version)

        print(f"\n{C_CYAN}{C_BOLD}--- Fabric Version Info ---{C_RESET}")
        print(f"  Loader     : {C_GREEN}{version_info.get('loader', 'unknown')}{C_RESET}")
        print(f"  Yarn       : {C_GREEN}{version_info.get('yarn', 'unknown')}{C_RESET}")
        print(f"  Fabric API : {C_GREEN}{version_info.get('fabric_api', 'unknown')}{C_RESET}")
        print(f"  Loom       : {C_GREEN}{version_info.get('loom', 'unknown')}{C_RESET}  {C_CYAN}(pinned, compatible){C_RESET}")
        print(f"  Gradle     : {C_GREEN}{version_info.get('gradle', 'unknown')}{C_RESET}")
        print(f"  Java       : {C_GREEN}{version_info.get('java', 21)}{C_RESET}")
        print(f"  Components : {C_GREEN}{'Yes' if version_info.get('data_components') else 'No (NBT)'}{C_RESET}")
        print(f"  Id.of()    : {C_GREEN}{'Yes' if version_info.get('identifier_of') else 'No (new Identifier)'}{C_RESET}")

        if input(f"\n{C_YELLOW}Override version info? (y/N): {C_RESET}").strip().lower() == "y":
            loader_ov = input(f"  Loader [{version_info.get('loader')}]: ").strip()
            if loader_ov: version_info["loader"] = loader_ov
            yarn_ov = input(f"  Yarn [{version_info.get('yarn')}]: ").strip()
            if yarn_ov: version_info["yarn"] = yarn_ov
            api_ov = input(f"  Fabric API [{version_info.get('fabric_api')}]: ").strip()
            if api_ov: version_info["fabric_api"] = api_ov
            loom_ov = input(f"  Loom [{version_info.get('loom')}] (WARNING: changing this may break builds): ").strip()
            if loom_ov: version_info["loom"] = loom_ov

        existing_context = ""
        if mode == "2":
            if force_path:
                project_dir = force_path
                mod_name = os.path.basename(os.path.normpath(project_dir))
            else:
                print(f"\n{C_YELLOW}{C_BOLD}--- Edit Directory ---{C_RESET}")
                tp = input("Path/name: ").strip().replace('"', '').replace("'", "")
                if not tp:
                    tp = os.path.join(default_base, input("Folder name: ").strip())
                elif not os.path.isabs(tp):
                    tp = os.path.join(default_base, tp)
                if not os.path.exists(tp):
                    print(f"{C_RED}[X] Not found.{C_RESET}")
                    return None
                project_dir = os.path.abspath(tp)
                mod_name = os.path.basename(os.path.normpath(project_dir))

            fmj_path = os.path.join(project_dir, "src", "main", "resources", "fabric.mod.json")
            if os.path.exists(fmj_path):
                try:
                    with open(fmj_path, "r", encoding="utf-8") as f:
                        fmj = json.load(f)
                    mod_id = fmj.get("id", mod_name.lower().replace(" ", "_"))
                except Exception:
                    mod_id = mod_name.lower().replace(" ", "_").replace("-", "_")
            else:
                mod_id = mod_name.lower().replace(" ", "_").replace("-", "_")

            for root, dirs, files in os.walk(project_dir):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                for file in files:
                    if file.endswith((".java", ".json", ".gradle", ".properties")):
                        try:
                            with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                                rel = os.path.relpath(os.path.join(root, file), project_dir)
                                existing_context += (f"\n\n================ FILE: {rel} "
                                                     f"================\n{f.read()}\n"
                                                     f"================ END ================\n")
                        except Exception:
                            pass
            idea = input(f"\n{C_YELLOW}Changes/fixes?{C_RESET}\n-> ")
            extra = input("Extra details: ").strip()
        else:
            mod_name = input("\nMod Name: ").strip()
            if not mod_name:
                return None
            mod_id = re.sub(r'[^a-z0-9_]', '_', mod_name.lower()).strip('_')
            custom_id = input(f" Mod ID [{C_CYAN}{mod_id}{C_RESET}]: ").strip()
            if custom_id:
                mod_id = re.sub(r'[^a-z0-9_]', '_', custom_id.lower()).strip('_')
            ub = input(f" Destination [{C_CYAN}{default_base}{C_RESET}]: ").strip().replace('"', '').replace("'", "") or default_base
            project_dir = os.path.abspath(os.path.join(ub, mod_id))
            os.makedirs(project_dir, exist_ok=True)
            idea = input("What should the mod do?\n-> ")
            extra = input("Extra: ").strip()

        pkg = f"com.example.{mod_id.replace('_', '')}"
        custom_pkg = input(f" Package [{C_CYAN}{pkg}{C_RESET}]: ").strip()
        if custom_pkg:
            pkg = custom_pkg
        mod_class_name = f"{_capitalize(mod_id)}Mod"
        custom_class = input(f" Main Class [{C_CYAN}{mod_class_name}{C_RESET}]: ").strip()
        if custom_class:
            mod_class_name = custom_class
        expected_main_path = f"src/main/java/{pkg.replace('.', '/')}/{mod_class_name}.java"

        vac = generate_fabric_version_constraints(mc_version, version_info)
        build_gradle_content = generate_build_gradle(pkg, mod_id, version_info, mc_version)
        settings_gradle_content = generate_settings_gradle()
        gradle_props_content = generate_gradle_properties(mc_version, version_info)
        fmj_content = generate_fabric_mod_json(mod_id, mod_name, pkg, mod_class_name, mc_version, version_info)
        mixin_content = generate_mixin_json(mod_id, pkg, version_info)
        main_class_content = generate_main_class(pkg, mod_class_name, mc_version, version_info)

        template_block = (
            f"================ FILE: build.gradle ================\n{build_gradle_content}\n================ END ================\n\n"
            f"================ FILE: settings.gradle ================\n{settings_gradle_content}\n================ END ================\n\n"
            f"================ FILE: gradle.properties ================\n{gradle_props_content}\n================ END ================\n\n"
            f"================ FILE: src/main/resources/fabric.mod.json ================\n{fmj_content}\n================ END ================\n\n"
            f"================ FILE: src/main/resources/{mod_id}.mixins.json ================\n{mixin_content}\n================ END ================\n\n"
            f"================ FILE: {expected_main_path} ================\n{main_class_content}\n================ END ================\n"
        )

        si = (
            f"You are an Elite Minecraft Fabric Mod Architect writing complete, production-grade mods.\n"
            f"Target: Fabric MC v{mc_version} using Gradle + Fabric Loom {version_info.get('loom')}. Java {version_info.get('java', 21)}.\n\n"
            f"{HARDCODED_FABRIC_MISTAKES}\n\n{vac}\n\n"
            f"CRITICAL: Write every line. No skeletons, placeholders, TODOs, or abbreviations.\n\n"
            f"FILES RULE: Generate ALL files including fabric.mod.json, mixin JSON, AND main mod class.\n"
            f"Main class '{mod_class_name}' at '{expected_main_path}'.\n"
            f"Package: '{pkg}'. Mod ID: '{mod_id}'.\n\n"
            f"DO NOT generate build.gradle, settings.gradle, or gradle.properties — these are managed by the tool and already correct.\n\n"
            f"FORMAT: Output files inside ================ FILE: path ================ blocks:\n\n"
            f"{template_block}\n\n"
            f"ALSO generate resource files as needed:\n"
            f"- src/main/resources/assets/{mod_id}/lang/en_us.json\n"
            f"- src/main/resources/assets/{mod_id}/models/item/*.json\n"
            f"- src/main/resources/assets/{mod_id}/models/block/*.json\n\n"
            f"If the mod needs client-only code, create a client entrypoint class.\n\n"
            f"NEVER import net.minecraft.client.* in server/common code.\n"
            f"NEVER use Bukkit/Spigot/Paper APIs.\n"
            f"ALWAYS use Yarn mappings (not Mojmap).\n"
        )

        if mode != "2":
            pt = (f"Build complete Fabric mod for MC {mc_version} using Gradle.\n"
                  f"Name: '{mod_name}' | Mod ID: '{mod_id}' | Package: '{pkg}' | "
                  f"Function: {idea} | Extra: {extra}\n\n"
                  f"EVERY method MUST use exact Yarn-mapped names. EVERY enum UPPERCASE. ALWAYS null-check.\n"
                  f"Include lang file and model JSONs.\n"
                  f"DO NOT modify build.gradle, settings.gradle, or gradle.properties.\n")
        else:
            pt = (f"Edit '{mod_name}' for Fabric MC {mc_version}.\nFiles:\n{existing_context}\n\n"
                  f"Changes: {idea} | Extra: {extra}\n\n"
                  f"Preserve correct code. Fix Yarn mappings/enums/null-checks.\n"
                  f"DO NOT modify build.gradle, settings.gradle, or gradle.properties.\n")

        raw_text = execute_browser_request(si, pt, project_dir, is_heal=False)

        ftw = parse_ai_response(raw_text, expected_main_path, pkg, mod_class_name, mod_id)
        if not ftw:
            print(f"{C_RED}[X] No file blocks found in AI response.{C_RESET}")
            return project_dir

        # Remove build files from AI response — we manage these
        for key in list(ftw.keys()):
            if key in ("build.gradle", "settings.gradle", "gradle.properties"):
                print(f"  {C_YELLOW}[!] Ignored AI's {key} (tool-managed){C_RESET}")
                del ftw[key]

        if not any("fabric.mod.json" in f for f in ftw):
            ftw["src/main/resources/fabric.mod.json"] = fmj_content
        if not any(f"{mod_id}.mixins.json" in f for f in ftw):
            ftw[f"src/main/resources/{mod_id}.mixins.json"] = mixin_content

        if mode == "1" and any(k.strip().startswith("src") for k in ftw.keys()):
            sp = os.path.join(project_dir, "src")
            if os.path.exists(sp):
                print(f"  {C_YELLOW}[!] Flushing previous sources...{C_RESET}")
                shutil.rmtree(sp, ignore_errors=True)

        for rfp, code in ftw.items():
            crp = os.path.normpath(rfp).replace("..", "")
            if crp.startswith(os.sep):
                crp = crp[1:]
            fop = os.path.join(project_dir, crp)
            os.makedirs(os.path.dirname(fop), exist_ok=True)
            with open(fop, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"  -> {C_CYAN}Synced:{C_RESET} {crp}")

        run_precompilation_fixes(project_dir, mod_id, mod_name, pkg, mod_class_name, mc_version, version_info)

        print(f"\n{C_GREEN}[OK] Files written! Compiling...{C_RESET}")
        build_success, build_log = execute_build(project_dir, config, version_info, mod_id, mc_version)

        _last_session.update({
            "provider": "browser", "model": "browser", "api_key": None,
            "system_instruction": si, "max_tokens": 65536,
            "mc_version": mc_version, "build_tool": "Gradle",
            "project_dir": project_dir, "config": config,
            "heal_attempt_count": 0, "previous_errors": [],
            "mod_id": mod_id, "mod_class_name": mod_class_name,
            "pkg": pkg, "expected_main_path": expected_main_path,
            "java_version": version_info.get("java", 21),
            "version_info": version_info,
        })

        if not build_success:
            build_success, build_log = run_healing_loop(
                project_dir, si, 65536, mc_version, config,
                mod_id, mod_class_name, pkg, expected_main_path, version_info,
                start_attempt=1, max_attempts=3)

        return project_dir

    except Exception as e:
        print(f"\n{C_RED}[X] Pipeline error: {e}{C_RESET}")
        import traceback
        traceback.print_exc()
        return None


# =================================================================
# MAIN
# =================================================================

def main():
    force_mode = None
    force_path = None
    current_project_dir = None
    while True:
        try:
            result = run_pipeline(force_mode=force_mode, force_path=force_path)
            if result and os.path.exists(result):
                current_project_dir = result
        except Exception as e:
            print(f"\n{C_RED}[X] Crash: {e}{C_RESET}")
        action, target = prompt_post_action_menu(current_project_dir)
        if action == "new":
            force_mode = None
            force_path = None
        elif action == "edit":
            force_mode = "2"
            force_path = target
        elif action == "heal":
            pd, loops = target
            continue_healing(pd, loops)
            force_mode = None
            force_path = None
        else:
            force_mode = None
            force_path = None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}[!] Interrupted.{C_RESET}")
        sys.exit(0)