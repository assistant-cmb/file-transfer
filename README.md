# File Transfer

把任意文件无损转换为 PNG 图片，也可以从 PNG 自动恢复原文件。项目提供功能一致、互相兼容的纯 Python 版和纯 Node.js 版；选择本机已有运行环境的版本即可，不需要同时安装两种环境。

所有处理都在本机完成。服务默认只监听 `127.0.0.1`，不会上传文件、发送遥测或访问云端。

## 选择版本

| 版本 | 运行要求 | 第三方依赖 | macOS | Windows |
| --- | --- | --- | --- | --- |
| Python | Python 3.11+ | 无 | `python-version/start.command` | `python-version/start.bat` |
| Node.js | Node.js 20+ | 无 | `node-version/start.command` | `node-version/start.bat` |

两个版本使用同一个 File Transfer Format v1.0：Python 生成的 PNG 可以用 Node.js 版恢复，反之亦然。

## 双击启动

### macOS

在 Finder 中打开所选版本目录，双击 `start.command`。服务启动后会自动打开默认浏览器。

如果首次运行提示没有执行权限，在终端执行一次：

```bash
chmod +x python-version/start.command node-version/start.command
```

如果 macOS 阻止打开，可在 Finder 中右键脚本并选择“打开”，或在“系统设置 → 隐私与安全性”中允许。

### Windows

在资源管理器中打开所选版本目录，双击 `start.bat`。服务启动后会自动打开默认浏览器。

终端窗口会显示本地访问地址。关闭终端窗口或按 `Ctrl+C` 即可停止服务。

## 网页操作

1. 选择“文件 → 图片”或“图片 → 文件”。
2. 点击选择区域，或者把文件拖入页面。
3. 点击转换按钮。
4. 校验通过后点击下载结果。

默认最大原文件大小为 100 MiB。生成的 PNG 必须保持原样；缩放、裁剪、调色或转成 JPEG 都会破坏数据，工具会拒绝校验失败的图片。

## Python CLI

在 `python-version` 目录运行：

```bash
python3 -m file_transfer encode path/to/input.zip
python3 -m file_transfer decode path/to/input.zip.png
python3 -m file_transfer inspect path/to/input.zip.png
python3 -m file_transfer inspect path/to/input.zip.png --json
python3 -m file_transfer serve --port 8765 --no-browser
```

可用 `-o` 或 `--output` 指定输出文件或解码输出目录。默认不会覆盖已有文件，而是自动添加 ` (1)`、` (2)` 等序号。

## Node.js CLI

在 `node-version` 目录运行：

```bash
node src/cli.js encode path/to/input.zip
node src/cli.js decode path/to/input.zip.png
node src/cli.js inspect path/to/input.zip.png
node src/cli.js inspect path/to/input.zip.png --json
node src/cli.js serve --port 8765 --no-browser
```

参数、JSON 结果和核心错误代码与 Python 版保持一致。

## 项目结构

```text
file-transfer/
├── FORMAT.md                 # 已冻结的 v1.0 二进制格式规范
├── REQUIREMENTS.md           # 项目需求
├── PLAN.md                   # 实施计划
├── shared/                   # 两版共用的浏览器界面与固定测试向量
├── python-version/           # 纯 Python 标准库实现
├── node-version/             # 纯 Node.js 标准库实现
└── tests/                    # 跨语言互操作测试
```

## 运行测试

Python 固定向量、损坏检测和往返测试：

```bash
cd python-version
python3 -m unittest discover -s tests -v
```

Node.js 固定向量、损坏检测和往返测试：

```bash
cd node-version
npm test
```

双向互操作测试（需要两种运行时，仅开发和发布验收需要）：

```bash
python3 -m unittest discover -s tests -p '*_test.py' -v
```

## 格式与安全说明

- 固定格式规范见 [FORMAT.md](./FORMAT.md)。
- PNG 内保存原文件名、64 位文件长度、SHA-256、格式版本和头部 CRC-32。
- 解码会检查 PNG 结构、魔数、版本、元数据、图片容量、零填充和 SHA-256。
- 文件名在恢复前会进行路径与平台安全处理。
- 格式提供完整性检查，不提供加密、身份认证、压缩或纠错能力。
- 旧 `0xAF` 图片格式和需要手工输入文件大小的早期 Python 格式不属于 v1.0。

## 常见问题

### 双击后提示找不到运行时

安装 Python 3.11+ 或 Node.js 20+ 中的任意一种，然后使用对应版本。无需安装另一种运行时。

### 为什么 PNG 可能比原文件大？

文件字节直接映射到 RGB 像素。对于 ZIP、视频或其他已压缩数据，PNG 通常无法再次有效压缩。

### 图片为什么无法恢复？

最常见原因是图片平台做了缩放或转码。请以“文件”方式发送原始 PNG，避免使用会优化图片的相册或聊天图片通道。
