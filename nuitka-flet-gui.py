import flet as ft
import os
import sys
import subprocess
import threading
import json
import shutil
import platform
from pathlib import Path
from nuitka.plugins.Plugins import loadPlugins, plugin_name2plugin_classes
from nuitka.utils.AppDirs import getCacheDir
from nuitka.utils.Download import getCachedDownloadedMinGW64

__version__ = "2025.8.8"

_sys = platform.system()
IS_WIN32 = _sys == "Windows"
IS_MAC = _sys in {"OSX", "Darwin"}
IS_LINUX = _sys == "Linux"
loadPlugins()
_plugins_list = {
    k: getattr(v[0], "plugin_desc", "")
    for k, v in plugin_name2plugin_classes.items()
    if not v[0].isDeprecated()
}
file_path = Path("app")
output_path = Path("./nuitka_output")
nuitka_cache_path = Path(getCacheDir("")).absolute()
download_mingw_urls = []
RUNNING_PROC = None
STOPPING_PROC = False
cmd_list = []
pip_args = []
pip_cmd = []
python_exe_path = Path(sys.executable).as_posix()
if python_exe_path.endswith("pythonw"):
    python_exe_path = python_exe_path[:-1]
elif python_exe_path.endswith("pythonw.exe"):
    python_exe_path = python_exe_path[:-5] + ".exe"


def plugin_checkbox_row(plugin_states, on_plugin_change):
    rows = []
    keys = list(_plugins_list.keys())
    for i in range(0, len(keys), 6):
        row = []
        for k in keys[i : i + 6]:
            row.append(
                ft.Checkbox(
                    label=k,
                    value=plugin_states[k],
                    tooltip=_plugins_list[k],
                    key=f"plugin_{k}",
                    on_change=lambda e, k=k: on_plugin_change(k, e.control.value),
                )
            )
        rows.append(ft.Row(row))
    return rows


def update_cmd(values, plugin_states, output):
    cmd = [python_exe_path, "-m", "nuitka"]
    for k, v in values.items():
        if k.startswith("--") and v:
            if isinstance(v, bool):
                if v:
                    cmd.append(k)
            elif k in ("--include-package", "--include-module", "--other-args"):
                cmd.extend(str(v).split(","))
            else:
                cmd.append(k)
                cmd.append(str(v))
        elif k == "file_path" and v:
            global file_path
            file_path = Path(v)
        elif k == "pip_args" and v:
            args = str(v).split()
            pip_args.clear()
            pip_args.extend(args)
            pip_cmd.clear()
            pip_cmd.extend([python_exe_path, "-m", "pip", "install"])
            pip_cmd.extend(pip_args)
            pips_path = (output_path / f"{file_path.stem}.pips").as_posix()
            pip_cmd.extend(["-t", pips_path])
            cmd.append(f"--include-data-dir={pips_path}=./")
    for k, v in plugin_states.items():
        if v:
            cmd.append(f"--enable-plugin={k}")
    cmd.append(file_path.as_posix())
    cmd_list.clear()
    cmd_list.extend(cmd)
    # 출력
    text = f"[Python]:\n{sys.version}\n[Build]"
    if pip_cmd:
        text += "\n" + " ".join(pip_cmd)
    text += "\n" + " ".join(cmd)
    output.controls.clear()
    output.controls.append(ft.Text(text))


def init_download_urls():
    global download_mingw_urls
    download_mingw_urls.clear()
    try:
        url = getCachedDownloadedMinGW64(
            target_arch=None, assume_yes_for_downloads=True, download_ok=True
        )
        if url:
            download_mingw_urls.append(url)
    except Exception:
        pass


def start_build(page, output, values, plugin_states):
    global RUNNING_PROC, STOPPING_PROC
    STOPPING_PROC = False
    update_cmd(values, plugin_states, output)
    output.controls.append(ft.Text("\n[빌드 시작]"))
    page.update()
    try:
        if pip_cmd:
            output.controls.append(ft.Text("[pip install] " + " ".join(pip_cmd)))
            page.update()
            subprocess.run(pip_cmd, check=True)
        RUNNING_PROC = subprocess.Popen(
            cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        if RUNNING_PROC.stdout:
            for line in RUNNING_PROC.stdout:
                if STOPPING_PROC:
                    RUNNING_PROC.terminate()
                    output.controls.append(ft.Text("[빌드 중단됨]"))
                    break
                output.controls.append(ft.Text(line.rstrip()))
                page.update()
        RUNNING_PROC.wait()
        output.controls.append(ft.Text("[빌드 종료]"))
    except Exception as ex:
        output.controls.append(ft.Text(f"[빌드 오류] {ex}"))
    finally:
        RUNNING_PROC = None
        page.update()


def main(page: ft.Page):
    page.title = f"Nuitka Flet Toolkit - v{__version__}"

    # Flet 데스크탑 window 속성 사용 (비공식, Flet Desktop에서만 동작)
    import tkinter as tk

    root = tk.Tk()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    # 아래 속성들은 Flet Desktop에서만 동작합니다.
    try:
        page.window.width = sw
        page.window.height = sh
        # page.window.left = 0
        # page.window.top = 0
        page.window.frameless = False
        page.window.resizable = True
        page.window.maximizable = True
        page.window.maximized = True
        # page.window.full_screen = True  # 전체화면 원할 때 주석 해제
    except Exception:
        pass
    root.destroy()

    # 상태 변수 정의
    values = {
        "file_path": str(file_path),
        "--output-filename": "",
        "--onefile": False,
        "--onefile-tempdir-spec": "",
        "--standalone": True,
        "--module": False,
        "--windows-disable-console": False,
        "--windows-icon": "",
        "--macos-disable-console": False,
        "--nofollow-imports": False,
        "--remove-output": False,
        "--no-pyi-file": False,
        "--jobs": "",
        "build_tool": "none",
        "--mingw64": False,
        "--clang": False,
        "--assume-yes-for-downloads": False,
        "--include-package": "",
        "--include-module": "",
        "--other-args": "",
        "pip_args": "",
        "--output-dir": str(output_path),
        "is_compress": False,
        "need_start_file": False,
    }
    plugin_states = {k: False for k in _plugins_list}
    output = ft.Column(scroll=ft.ScrollMode.ALWAYS, height=200)

    def on_plugin_change(k, v):
        plugin_states[k] = v
        update_cmd(values, plugin_states, output)
        page.update()

    def on_change(e):
        # RadioGroup은 e.control.value, 일반 컨트롤은 e.control.key/value
        k = getattr(e.control, "key", None)
        v = getattr(e.control, "value", None)
        # RadioGroup: module_type
        if hasattr(e.control, "content") and hasattr(e.control, "value"):
            # module_type RadioGroup
            if e.control.value == "--standalone":
                values["--standalone"] = True
                values["--module"] = False
            else:
                values["--standalone"] = False
                values["--module"] = True
        elif k == "build_tool":
            values["build_tool"] = v
            values["--mingw64"] = v == "mingw64"
            values["--clang"] = v == "clang"
        elif k is not None:
            values[k] = v
        update_cmd(values, plugin_states, output)
        page.update()

    def on_start(e):
        if RUNNING_PROC:
            return
        threading.Thread(
            target=start_build, args=(page, output, values, plugin_states), daemon=True
        ).start()

    def on_cancel(e):
        global STOPPING_PROC
        STOPPING_PROC = True

    def on_view(e):
        if output_path.is_dir():
            if IS_WIN32:
                os.startfile(output_path)
            else:
                subprocess.run(
                    ["open" if IS_MAC else "xdg-open", str(output_path.absolute())]
                )

    def on_remove(e):
        if output_path.is_dir():
            shutil.rmtree(output_path)
            output.controls.append(ft.Text("Output 폴더 삭제됨"))
            page.update()

    def on_dump_config(e):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        file_path_ = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON files", "*.json")]
        )
        if not file_path_:
            return
        try:
            text = json.dumps(
                {**values, **{f"plugin_{k}": v for k, v in plugin_states.items()}},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            with open(file_path_, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as ex:
            output.controls.append(ft.Text(f"Config 저장 오류: {ex}"))
            page.update()

    def on_load_config(e):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        file_path_ = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path_:
            return
        try:
            with open(file_path_, encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if k.startswith("plugin_"):
                    plugin_states[k[7:]] = v
                else:
                    values[k] = v
            update_cmd(values, plugin_states, output)
            page.update()
        except Exception as ex:
            output.controls.append(ft.Text(f"Config 불러오기 오류: {ex}"))
            page.update()

    def on_nuitka_cache(e):
        size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(nuitka_cache_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    size += os.path.getsize(fp)
            output.controls.append(
                ft.Text(
                    f"NUITKA_CACHE_DIR: {nuitka_cache_path}\n용량: {size / 1024**3:.2f} GB"
                )
            )
            if IS_WIN32:
                os.startfile(nuitka_cache_path)
            else:
                subprocess.run(
                    ["open" if IS_MAC else "xdg-open", str(nuitka_cache_path)]
                )
            init_download_urls()
            output.controls.append(ft.Text("mingw64 다운로드 URL:"))
            for url in download_mingw_urls:
                output.controls.append(ft.Text(url))
            page.update()
        except Exception as ex:
            output.controls.append(ft.Text(f"캐시 정보 오류: {ex}"))
            page.update()

    # UI
    adv_option_row = ft.Row(
        controls=[
            ft.RadioGroup(
                value="--standalone" if values["--standalone"] else "--module",
                on_change=on_change,
                content=ft.Row(
                    controls=[
                        ft.Radio(label="--standalone", value="--standalone"),
                        ft.Radio(label="--module", value="--module"),
                    ]
                ),
            ),
            *(
                [
                    ft.Checkbox(
                        label="--windows-disable-console",
                        value=values["--windows-disable-console"],
                        on_change=on_change,
                    ),
                    ft.TextField(
                        label="--windows-icon",
                        value=values["--windows-icon"],
                        on_change=on_change,
                        width=180,
                    ),
                ]
                if IS_WIN32
                else []
            ),
            *(
                [
                    ft.Checkbox(
                        label="--macos-disable-console",
                        value=values["--macos-disable-console"],
                        on_change=on_change,
                    ),
                ]
                if IS_MAC
                else []
            ),
        ]
    )

    page.add(
        ft.Row(
            controls=[
                ft.Text("Entry Point:"),
                ft.TextField(
                    value=values["file_path"],
                    key="file_path",
                    on_change=on_change,
                    width=300,
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.Text("Output Name:"),
                ft.TextField(
                    value=values["--output-filename"],
                    key="--output-filename",
                    on_change=on_change,
                    width=150,
                ),
                ft.Checkbox(
                    label="--onefile",
                    value=values["--onefile"],
                    key="--onefile",
                    on_change=on_change,
                ),
                ft.TextField(
                    value=values["--onefile-tempdir-spec"],
                    key="--onefile-tempdir-spec",
                    on_change=on_change,
                    width=200,
                ),
            ]
        ),
        adv_option_row,
        ft.Row(
            controls=[
                ft.Checkbox(
                    label="--nofollow-imports",
                    value=values["--nofollow-imports"],
                    key="--nofollow-imports",
                    on_change=on_change,
                ),
                ft.Checkbox(
                    label="--remove-output",
                    value=values["--remove-output"],
                    key="--remove-output",
                    on_change=on_change,
                ),
                ft.Checkbox(
                    label="--no-pyi-file",
                    value=values["--no-pyi-file"],
                    key="--no-pyi-file",
                    on_change=on_change,
                ),
                ft.Text("--jobs:"),
                ft.TextField(
                    value=values["--jobs"], key="--jobs", on_change=on_change, width=60
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.RadioGroup(
                    value=values["build_tool"],
                    on_change=on_change,
                    content=ft.Row(
                        controls=[
                            ft.Radio(label="--mingw64", value="mingw64"),
                            ft.Radio(label="--clang", value="clang"),
                            ft.Radio(label="None", value="none"),
                        ]
                    ),
                ),
                ft.Checkbox(
                    label="--assume-yes-for-downloads",
                    value=values["--assume-yes-for-downloads"],
                    key="--assume-yes-for-downloads",
                    on_change=on_change,
                ),
            ]
        ),
        ft.Text("Plugins:"),
        *plugin_checkbox_row(plugin_states, on_plugin_change),
        ft.Row(
            controls=[
                ft.Text("--include-package:"),
                ft.TextField(
                    value=values["--include-package"],
                    key="--include-package",
                    on_change=on_change,
                    width=300,
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.Text("--include-module:"),
                ft.TextField(
                    value=values["--include-module"],
                    key="--include-module",
                    on_change=on_change,
                    width=300,
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.Text("Custom Args(,):"),
                ft.TextField(
                    value=values["--other-args"],
                    key="--other-args",
                    on_change=on_change,
                    width=300,
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.Text("Pip Args:"),
                ft.TextField(
                    value=values["pip_args"],
                    key="pip_args",
                    on_change=on_change,
                    width=300,
                ),
            ]
        ),
        ft.Row(
            controls=[
                ft.Text("Output Path:"),
                ft.TextField(
                    value=values["--output-dir"],
                    key="--output-dir",
                    on_change=on_change,
                    width=300,
                ),
                ft.ElevatedButton("View", on_click=on_view),
                ft.ElevatedButton("Remove", on_click=on_remove),
            ]
        ),
        ft.Row(
            controls=[
                ft.ElevatedButton("Start", on_click=on_start),
                ft.ElevatedButton("Cancel", on_click=on_cancel),
                ft.Checkbox(
                    label="Compress",
                    value=values["is_compress"],
                    key="is_compress",
                    on_change=on_change,
                ),
                ft.Checkbox(
                    label="shortcut.bat",
                    value=values["need_start_file"],
                    key="need_start_file",
                    on_change=on_change,
                ),
                ft.ElevatedButton("dump_config", on_click=on_dump_config),
                ft.ElevatedButton("load_config", on_click=on_load_config),
                ft.ElevatedButton("nuitka_cache", on_click=on_nuitka_cache),
            ]
        ),
        output,
    )
    update_cmd(values, plugin_states, output)
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
