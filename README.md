# File Transfer

把任意单个文件转换成图片，并从图片恢复原文件名和完整字节。项目同时提供两种互不混用的格式：

- **PNG v1**：无损、高容量，适合按“文件/文档”发送；图片必须保持原样。
- **JPEG v2**：带 Reed-Solomon 纠错，适合会轻度 JPEG 重压缩或等比缩放的聊天图片通道；容量较小。

Python 版和 Node.js 版遵循相同格式，可以相互恢复对方生成的图片。所有转换均在本机完成；服务默认只监听 `127.0.0.1`，不上传文件、不发送遥测。只有首次运行 `setup` 安装依赖时需要联网。

## 选择版本

| 版本 | 运行要求 | 图片依赖 | macOS 启动 | Windows 启动 |
| --- | --- | --- | --- | --- |
| Python | Python 3.11+ | Pillow 12.3.0 | `python-version/start.command` | `python-version/start.bat` |
| Node.js | Node.js 20.9.0+ | sharp 0.35.3 | `node-version/start.command` | `node-version/start.bat` |

只需选择本机已有运行环境的一版，不需要同时安装 Python 和 Node.js。

## 首次安装依赖

安装脚本只在用户主动运行时联网。正常启动和文件处理不会自动下载依赖。

### macOS

在 Finder 中打开所选版本目录，先双击 `setup.command`。安装完成后双击 `start.command`。

如果脚本没有执行权限，在终端执行一次：

```bash
chmod +x python-version/setup.command python-version/start.command
chmod +x node-version/setup.command node-version/start.command
```

如果 macOS 阻止打开，可在 Finder 中右键脚本并选择“打开”，或在“系统设置 → 隐私与安全性”中允许。

Python 安装脚本会在 `python-version/.venv` 创建独立虚拟环境，不修改系统 Python。Node.js 安装脚本使用锁定文件执行 `npm ci`。

### Windows

在资源管理器中打开所选版本目录，先双击 `setup.bat`，安装完成后双击 `start.bat`。

终端窗口会显示本地访问地址。关闭终端窗口或按 `Ctrl+C` 即可停止服务。

## 选择 PNG v1 还是 JPEG v2

| 特性 | PNG v1 | JPEG v2 |
| --- | --- | --- |
| 最大原文件 | 100 MiB | 100 KiB（102,400 字节） |
| 图片通道 | 必须无损保持原样 | 可承受常见的轻度 JPEG 重压缩与适度等比缩放 |
| 纠错 | 无；CRC/SHA 只负责发现损坏 | RS(255,179) + 三份 manifest + CRC/SHA |
| 典型用途 | 按文件发送、归档、大文件 | 小型 ZIP、配置等经聊天图片通道传递 |
| 可选 ZIP 包装 | 支持把生成的 PNG 装入 ZIP | 不支持；应直接把原 ZIP 作为载荷编码 |

JPEG v2 的标准编码质量固定为 **95**，每个黑白数据模块为 4 × 4 像素。输出分辨率由原文件和 UTF-8 文件名共同决定，短文件名时大致如下：

| 原文件大小 | JPEG v2 推荐输出分辨率 |
| ---: | ---: |
| 1 KiB | 584 × 584 |
| 10 KiB | 1544 × 1544 |
| 25 KiB | 2376 × 2376 |
| 50 KiB | 3312 × 3312 |
| 75 KiB | 4032 × 4032 |
| 100 KiB | 4644 × 4644 |

100 KiB 文件加上最长 1024 字节文件名时可达到约 4664 × 4664。JPEG 文件在磁盘上的大小不等于它能承载的原文件大小；JPEG 体积还受图像内容、编码器和聊天平台再次压缩影响。

JPEG v2 **不能裁剪**。请发送完整图片并保留四周白色静区；不要截图、加边框、水印、滤镜、透视变形或非等比拉伸。纠错能力有上限，平台压缩或缩放过重时仍会恢复失败，并以最终 SHA-256 校验为准。

## 网页操作

1. 双击对应版本的启动脚本，等待浏览器打开本地页面。
2. 选择“文件 → 图片”或“图片 → 文件”。
3. 选择 **PNG v1** 或 **JPEG v2**。
4. 点击选择区域，或者把文件拖入页面。
5. 点击转换按钮，校验通过后下载结果。

PNG v1 的“转换后打包为 ZIP”只会把生成的 PNG 放进 ZIP。接收方必须先解压，再选择其中的 PNG 恢复文件。

## Python CLI

在 `python-version` 目录运行。macOS/Linux 完成 setup 后可使用 `.venv/bin/python`；下面用 `python3` 简写：

```bash
# PNG v1
python3 -m file_transfer encode path/to/input.zip
python3 -m file_transfer encode path/to/input.zip --zip

# JPEG v2
python3 -m file_transfer encode path/to/input.zip --format jpeg

# decode / inspect 会按 JPEG SOI 自动分派 v1 或 v2
python3 -m file_transfer decode path/to/input.zip.png
python3 -m file_transfer decode path/to/input.zip.jpg
python3 -m file_transfer inspect path/to/input.zip.jpg --json

python3 -m file_transfer serve --port 8765 --no-browser
```

可用 `-o` 或 `--output` 指定输出文件或解码输出目录。默认不会覆盖已有文件，而是自动添加 ` (1)`、` (2)` 等序号。`--format jpeg` 与 `--zip` 互斥；要传 ZIP，请直接把原 ZIP 编码为 JPEG v2。

Windows 虚拟环境的解释器位于 `.venv\Scripts\python.exe`。

## Node.js CLI

在 `node-version` 目录运行：

```bash
# PNG v1
node src/cli.js encode path/to/input.zip
node src/cli.js encode path/to/input.zip --zip

# JPEG v2
node src/cli.js encode path/to/input.zip --format jpeg

# decode / inspect 会按 JPEG SOI 自动分派 v1 或 v2
node src/cli.js decode path/to/input.zip.png
node src/cli.js decode path/to/input.zip.jpg
node src/cli.js inspect path/to/input.zip.jpg --json

node src/cli.js serve --port 8765 --no-browser
```

参数、JSON 结果和核心格式校验与 Python 版保持一致。

## 项目结构

```text
file-transfer/
├── FORMAT.md                 # 已冻结的无损 PNG v1.0 规范
├── FORMAT_V2.md              # 已冻结的容错 JPEG v2 profile 1 规范
├── REQUIREMENTS.md           # 初始项目需求
├── PLAN.md                   # 实施计划
├── shared/                   # 两版共用的浏览器界面与固定测试向量
├── python-version/           # Python、Pillow、CLI 与本地服务
├── node-version/             # Node.js、sharp、CLI 与本地服务
└── tests/                    # 跨语言互操作测试
```

## 运行测试

Python 测试：

```bash
cd python-version
.venv/bin/python -m unittest discover -s tests -v
```

Node.js 测试：

```bash
cd node-version
npm test
```

双向互操作测试需要两种运行时及其依赖：

```bash
python3 -m unittest discover -s tests -p '*_test.py' -v
```

测试覆盖 v1 固定向量与损坏检测、v2 manifest/RS/JPEG/缩放恢复，以及 Python 与 Node.js 的双向恢复。

## 格式与安全说明

- PNG v1 规范见 [FORMAT.md](./FORMAT.md)；JPEG v2 规范见 [FORMAT_V2.md](./FORMAT_V2.md)。
- 两种格式都会保存原文件名和长度，并在成功输出前校验完整性。
- PNG v1 将文件字节直接映射到 RGB，提供 CRC-32/SHA-256 检错，但没有纠错能力。
- JPEG v2 以黑白模块承载三份 manifest 与交织 RS 数据，最终校验 body 的 CRC-32 和 SHA-256。
- 文件名在恢复前会进行路径与平台安全处理。
- 两种格式都不提供加密或身份认证；任何能够读取图片的人都可能恢复其中的文件。
- 旧 `0xAF` 图片格式和需要手工输入文件大小的早期 Python 格式不属于 v1/v2。

## 常见问题

### 启动脚本提示缺少 Pillow 或 sharp

关闭启动窗口，在对应版本目录运行一次 `setup.command` 或 `setup.bat`，再重新启动。setup 会联网下载锁定版本；start 本身不会联网安装。

### 为什么 PNG v1 无法恢复？

最常见原因是图片平台做了缩放或有损转码。请改用 JPEG v2（文件不超过 100 KiB），或者把 PNG 以“文件/文档”方式发送。

### JPEG v2 变成 JPEG 后为什么仍能恢复？

v2 不依赖每个像素完全相等。它使用较大的黑白模块、定位与同步图案、三份 manifest、交织 Reed-Solomon 纠错和最终哈希校验。它只能容忍设计范围内的改变，不代表任意 JPEG 编辑都可恢复。

### 为什么 JPEG v2 无法恢复？

确认图片没有被裁剪、截图、旋转、加水印或非等比拉伸，并保留完整白色边缘。平台若把 4644 像素的大图压得过小，也可能低于解码所需的模块分辨率。可先减少原文件大小后重新编码。

### 为什么 PNG 或 JPEG 可能比原文件大？

图片是传输载体，不是普通压缩包。PNG v1 对 ZIP、视频等已压缩数据通常无法再次有效压缩；JPEG v2 还为黑白模块、定位区和纠错数据付出较大冗余。
