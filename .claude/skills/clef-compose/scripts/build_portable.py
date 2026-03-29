"""打包 clef_tools 为单文件可执行程序（使用 PyInstaller）。"""
import subprocess
import sys
import os


def build():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    entry = os.path.join(scripts_dir, 'clef_tools.py')
    dist_dir = os.path.join(scripts_dir, '..', 'dist')

    # hidden imports for music21 and mido
    hidden = [
        'music21', 'music21.converter', 'music21.key',
        'music21.pitch', 'music21.meter', 'music21.note',
        'music21.stream', 'music21.interval', 'music21.voiceLeading',
        'music21.harmony', 'music21.corpus', 'music21.common',
        'mido', 'mido.backends',
    ]

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--name', 'clef_tools',
        '--distpath', dist_dir,
        '--workpath', os.path.join(scripts_dir, '..', 'build', 'pyinstaller'),
        '--specpath', scripts_dir,
        '--noconfirm',
    ]
    for h in hidden:
        cmd.extend(['--hidden-import', h])

    cmd.append(entry)

    print("Building clef_tools.exe ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"BUILD FAILED:\n{result.stderr}")
        return 1

    exe_path = os.path.join(dist_dir, 'clef_tools.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"OK: {exe_path} ({size_mb:.1f} MB)")
    else:
        print("BUILD FAILED: output not found")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(build())
