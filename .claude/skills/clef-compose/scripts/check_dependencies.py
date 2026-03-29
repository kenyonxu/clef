"""检查 clef-compose v2 所需的 Python 依赖。"""
import importlib
import io
import sys


def check() -> bool:
	issues = []
	for pkg in ['music21', 'mido']:
		try:
			importlib.import_module(pkg)
			print(f"  [OK] {pkg}")
		except ImportError:
			issues.append(pkg)

	if issues:
		print(f"  [MISSING] 缺失: {', '.join(issues)}")
		print(f"  安装: pip install {' '.join(issues)}")
		return False
	print("所有依赖已就绪。")
	return True


if __name__ == '__main__':
	# 修复 Windows GBK 编码下无法输出 Unicode 的问题
	if hasattr(sys.stdout, 'buffer'):
		sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
		sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
	sys.exit(0 if check() else 1)
