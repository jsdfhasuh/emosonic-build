# EmoSonic Android + Windows builder

固定从私有 `jsdfhasuh/emosonic` 的 **`refs/heads/master`** 构建正式签名 Android APK 和 Windows x64 Inno Setup 安装包，统一发布到公开 [emosonic-releases](https://github.com/jsdfhasuh/emosonic-releases)。公开仓库只保存自编构建基础设施，不保存产品源码、keystore 或 token；不构建 iOS。

**[1.0.9+26](https://github.com/jsdfhasuh/emosonic-releases/releases/tag/v1.0.9%2B26) 已于 2026-10-18 01:20:22 UTC 发布为 stable latest。** [运行 39085337807](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39085337807) 六个 jobs 全部成功；104 项真实 Java 契约、完整 Android debug 编译、正式签名 release、双平台独立验包均通过。六个公开资产已重新下载，大小、摘要与双 manifest 全部吻合。固定 source `ecd827ec605577c31f3abcc3390fd53baf22df4c`、builder `f82d257f53fff083d6ebdfaa4b5a9965f51961f9`。[完整验证报告](docs/validation/2026-10-18-native-ack-log-sharing-release.md)。真机与覆盖安装验收仍待用户完成；手机签名冲突未解决，勿卸载或清除数据来强制安装。

历史正式版 [1.0.8+25 验证报告](docs/validation/2026-10-17-offline-remediation-release.md) 与 [1.0.7+24 验证/首次失败记录](docs/validation/2026-10-17-offline-stable-release.md)保留，历史 F02 PARTIAL/OPEN 结论不改写。构建脚本不会自动修改或虚增源码版本。

## 固定离线候选测试包

单独的 `offline-candidate.yml` 仅为已授权的离线候选 `601d6b4` 构建 Android 测试包；它不会发布 Release，也不改下面的正式发布流程。入口限定 `main`、专用 request 文件、固定上一提交及完整提交消息，后续普通提交不会自动签名。测试版显示 `1.0.6-offline.601d6b4`、保留 versionCode 23；先对既有正式 APK 做真实验包。须手动安装并先备份数据，旧版回退不保证安全。完整边界见[候选测试计划](docs/plans/2026-10-17-offline-candidate.md)。

已验证测试包：[Actions run 39025031880](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39025031880)，builder `98936d5b981b16df231a08964b03af7a1007b667`，53项流水线测试通过。APK SHA-256：`106dfd07980f86c8756689995620bfd9387686c47d8c3a59f95fd1568f076f6a`。CI原始artifact于2026-10-18 10:37:50 UTC过期。实际安装、离线浏览/播放及数据兼容性未验收。

## 本次授权的固定正式发布

本次原生 ACK 与日志分享发布请求为 `requests/stable-1.0.9-26.json`，固定源码 `ecd827ec605577c31f3abcc3390fd53baf22df4c`、版本 `1.0.9+26`，绑定 builder 上一提交 `8b015c2cf4c86397acbe2491569fcb4b999f103b` 与完整提交消息。只授权这一次受限 main push，普通 push 不会签名或发布，手动模式保持不变。[本次计划](docs/plans/2026-10-17-native-ack-log-share-release.md)。完整 Flutter 测试 2442/2442、全项目分析、代码生成、导航检查、原四反例及来源校验已通过，源文件零变动；独立13项边界复核与104项Java契约通过。现已完成正式打包、独立验包、六资产下载复核和 latest 确认，见上方验证报告。

Android 签名文件写入前，先由 Temurin 17 `javac --release 8` 编译实际生产 NativeStartGate 与已提交的 Java main 测试，`java -ea` 运行并强制匹配 104 检查成功标记；缺源码、缺 class、执行失败或数量不符均停止。随后完整 debug APK 编译确认实际 vendored just_audio Android 代码可构建，再正式签名 release 编译。两平台同源与独立验包、六资产及 stable latest 门禁不变。此处不是 JUnit 测试，也不代表设备音频通过。

本次完成 Android 实际 Media3 播放状态的即时开始事实通道，并整合当前/上次诊断日志的有界脱敏分享。真机、覆盖安装、后台媒体控制与真实出声仍待用户验收。如 Android 提示签名不一致，请停止，勿卸载原应用或清除数据；历史 GitHub 证书一致不能证明与手机现装 APK 兼容。上一版 1.0.8+25 的 F02 限制与结果留在历史[验证报告](docs/validation/2026-10-17-offline-remediation-release.md)。

## 每次只选择运行模式

1. 开发时，在产品仓库 `pubspec.yaml` 更新唯一版本行并提交到 master，例如 `version: 1.0.6+24`（仅格式示例，不代表已选定发行版本）。使用未加引号、无行尾注释的单行 `X.Y.Z+BUILD`。不接受重复 version 键、别名、合并或多文档 YAML。版本名不得降低，build number 必须严格高于所有已存在 releases/tags 和基线 23；四段数字均不能超过 Windows 版本资源上限 65535。
2. 在下述 Environments 配置好 Secrets。
3. 打开 [Actions 工作流](https://github.com/jsdfhasuh/emosonic-build/actions/workflows/android.yml)，选择 **Android + Windows stable → Run workflow → main**。页面只需选择 `mode`，无需填写源码 ref、SHA 或版本。工作流文件仍为 `android.yml`，保留原有链接。
4. 首次选择 `build-only`：构建并独立验证两个平台，只上传一天有效的分发 artifacts，不创建 Release。每个平台只有安装包、同名 `.sha256` 和脱敏 manifest。
5. 下载两个平台安装包，分别验证覆盖安装、配置保留、普通曲库播放和应用内更新。验证后，再选择 `publish-stable`：重新读取当时 master 的提交和版本，重建两个平台、验证并发布。若希望发布与试构建相同的源码，请在两次运行间保持 master 不变并核对 manifest 的 source SHA；这不是对先前 artifact 的直接推广。

`prepare` 只解析一次固定 master，并按得到的完整 SHA 读取 `pubspec.yaml`。两个构建 job、两个验证 job 和发布 job 都使用同一 SHA 和版本；即使分支随后前进，本次运行也不会追随。每次新的手动运行可直接接纳新的 master 提交，无需维护提交白名单。其他分支、tag、任意 ref 和手动版本覆盖均不可用。每个构建 job 还会核对检出的源码版本与 prepare 完全一致。

版本冲突时会提示 `Update pubspec.yaml on master`，且 prepare 不输出任何可用于构建的版本或 SHA。不能靠只提高版本名复用旧 build number，也不能覆盖已有 tag、Release 或资产。

## Environment / Secrets 配置

沿用 `android-build`、`android-release`，另有 `windows-build`；`android-release` 负责两个平台的统一发布。

1. 在 [Environments](https://github.com/jsdfhasuh/emosonic-build/settings/environments) 创建上述环境，Deployment branches and tags **只允许 main**。建议为发布环境设置人工审批并保护 builder 的 main。此任务不改变账户或 Environment 权限。
2. 用户亲自创建两个不同的 [Fine-grained PAT](https://github.com/settings/personal-access-tokens)，Resource owner=`jsdfhasuh`，Only select repositories，设置到期日：

   | Secret | 唯一所选仓库 | 最小 Repository permissions |
   | --- | --- | --- |
   | `SOURCE_READ_TOKEN` | `jsdfhasuh/emosonic` | Contents: Read-only；Metadata 自动只读 |
   | `RELEASE_WRITE_TOKEN` | `jsdfhasuh/emosonic-releases` | Contents: Read and write；Metadata 自动只读 |

   无需其他仓库、Actions、Workflows 或管理写权限。新 release tag 指向发布仓库的默认分支提交，不指向私有源码提交。
3. 用户亲自填写 Environment Secrets：

   | 环境 | Secrets |
   | --- | --- |
   | `android-build` | `SOURCE_READ_TOKEN`、`DEFAULT_SERVER_URL`、`ANDROID_KEYSTORE_BASE64`、`ANDROID_STORE_PASSWORD`、`ANDROID_KEY_PASSWORD`、`ANDROID_KEY_ALIAS` |
   | `windows-build` | `SOURCE_READ_TOKEN`、`DEFAULT_SERVER_URL` |
   | `android-release` | `RELEASE_WRITE_TOKEN` |

   Windows 环境由用户填写与 Android 相同的只读 PAT 和服务地址，不继承 Android 签名 Secrets。原 Windows 安装包没有 Authenticode 签名，继续保留该行为，不新增签名 Secret。
4. Android 必须使用**原正式 keystore、密码和 alias**，base64 编码为单行。缺少 Secrets 就停止，不生成替代证书或使用 debug 签名。两个平台的 `DEFAULT_SERVER_URL` 须与原应用保持一致，使用不含账户、密码、query 或 fragment 的 HTTPS URL；Windows 批处理接口还不接受 `%`、引号、空格等 cmd 特殊字符。
5. 保持默认 `GITHUB_TOKEN` 只读。若账户限制第三方 Actions，需允许 workflow 中已固定完整 SHA 的 Actions。

[Actions Secrets 设置入口](https://github.com/jsdfhasuh/emosonic-build/settings/secrets/actions)。不要把发布 PAT 放进 build 环境，也不要把凭据贴到聊天、issue、代码、Variables 或 workflow 输入。助手不会创建、读取、复制或填写凭据；旧仓库 Secrets 不会自动继承。服务地址虽以 Secret 传入，但会嵌入应用二进制，因此不能把它当作认证凭据；公开 manifest 不记录该地址。

## 原应用内更新与发布

Android 和 Windows 继续查询 `jsdfhasuh/emosonic-releases/releases/latest`，标签使用 `vX.Y.Z+N`。原客户端 Android 选择 `.apk`，Windows 选择 `.exe`/`.msi`，不会扫描历史 Release 来补齐缺少的平台。只有两个平台都从同一源码提交及版本构建、独立验证通过，并且六个资产完整上传校验后，草稿才转为正式 Release/latest。

资产为 `emosonic_android_vX.Y.Z+N.apk`、`emosonic_windows_vX.Y.Z+N_setup.exe`、各自 `.sha256`、`android-manifest.json` 和 `windows-manifest.json`。不发布 Android-only latest、不用旧 Windows 包冒充新版本、不使用旧客户端无法解析的 `android-v...` 标签。

不要同时用旧产品仓库的手动 workflow 发布同一版本。本仓库 concurrency 只能串行本仓库运行，无法与另一个独立 publisher 实现原子互斥。发布前及草稿推广前重复检查 release/tag 历史和 latest；已有同名对象就停止，不覆盖、不接管、不复用旧资产。上传或校验失败保留草稿供检查，不自动删除或重试写入。新版本异常应停止分发并用更高 build 修复，不用旧 build 覆盖回滚。

## 信任边界与兼容维护

用户已选择持续信任私有 master 的维护者、构建脚本及其依赖。取消逐提交审查和 Windows 脚本/模板整文件 blob 锁后，普通源码变更不需要同步修改本仓库。**这意味着 master 中的构建代码可以在 build runner 执行；入口文件存在检查不是代码沙箱。** 原签名材料也必须短暂提供给 Android 编译流程，受信任源码仍有接触它们的能力。

| Job | 权限与职责 |
| --- | --- |
| `prepare` | 仅 builder main 手动或本次严格固定 push；只读解析 master、读取同一 SHA 的版本、检查发布历史 |
| `build` | Linux Android 构建；只读源码 PAT 仅在 fetch 步骤注入；正式签名 Secrets |
| `build-windows` | Windows 2022；只读源码 PAT 仅在 fetch 步骤注入；服务地址及固定编译器配置 |
| `verify` / `verify-windows` | 独立新 runner；无用户 Secrets；只解析产物，不安装或运行应用 |
| `publish` | 独立 Linux runner；发布 PAT 仅最后一步注入；不执行私有源码或安装包 |

checkout 固定 builder 本次 SHA，`persist-credentials: false`。源码 PAT 只用于静默 fetch，不写入 git 配置；构建子进程环境剔除 PAT 与签名 Secret 环境变量。Actions 固定完整提交 SHA。正式发布工作流只接受手动入口及上述一次性固定授权 push，不接受 pull_request_target、公众评论或普通 push；独立候选工作流只接受其一次性固定 push。

Android 固定包名 `com.example.emosonic` 和原证书 SHA-256 `6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`，独立检查签名、版本、非 debug 和三个 ABI。Windows 独立检查 AppId `{779F17F8-DA99-4D5B-A404-E7E2D17C1E65}`、安装目录 `{localappdata}\Programs\EmoSonic`、权限 `lowest`、`emosonic.exe`、x64 PE、内嵌版本及完整运行载荷；改文件名或 manifest 不能把旧二进制变成新版本。

以下接口变化仍需维护构建基础设施，而非重新添加每个源码 SHA：

- Flutter/Dart SDK 要求或 Android 签名配置路径、包名、ABI 变化。
- `build_windows.bat` 无参数构建入口，以及 `DEFAULT_SERVER_URL`、`APP_UPDATE_SOURCE`、`GITHUB_RELEASE_REPOSITORY`、`INNO_SETUP_COMPILER` 环境接口变化。
- Windows 原 Inno 模板路径 `windows/installer/emosonic.iss`、安装包输出目录 `build/windows/installer`、资产命名或安装身份变化。
- 导航检查、build_runner 或包解析流程发生不兼容变更。

Windows 继续调用受信任 master 的原构建入口且不传 `--upload`，pubspec 保持原样，不再临时替换版本。Android build-name/build-number 也仅来自同一源码版本。构建器自身只下载 policy 中固定 URL/哈希的 Inno Setup 6.7.3、innounp 2.71.2；不会因源脚本变化自动选择或下载替代工具。私有构建脚本和依赖自身的网络行为属于对 master 的信任范围，固定工具哈希不等于网络沙箱。

每份 schema 3 manifest 包含固定来源仓库/分支、解析出的 SHA、builder SHA、run ID/attempt、版本、平台身份和包摘要。发布步骤比对双平台元数据、独立 verifier 摘要和远程上传资产的大小/摘要，再推广 latest。

## 隐私与真实验收边界

**公开 Actions 无法提供绝对源码保密保证。** 工具和编译器 stdout/stderr 被抑制，私有源码、原始日志、调试符号和凭据不上传；只上传校验后的分发文件。源码、工具或依赖仍拥有 build runner 上的执行能力，可能泄露或嵌入其他私有文件；扩展名扫描和 PAT masking 无法替代信任。需要强保密时应使用私有或隔离构建环境。失败时在受控私有环境诊断，不启用公开 runner debug 或上传源码/环境转储。

固定 Flutter 3.41.2 及其 SDK SHA、Java 17 和 Android build-tools 36.0.0。本次固定源码包含 pubspec.lock；依赖锁并不保证 SDK、原生工具链和所有远程依赖绝对可重复。本仓库不公开私有产品源码或依赖缓存。

两平台的覆盖安装、配置保留、普通曲库播放及应用内更新仍需真实验收。严格实时连接另需服务端符合 protocol 2.9 / r19 的认证 ACK；配套服务端合并/部署未验证，不能将实时协议不兼容直接判定为普通曲库播放失败。本仓库不部署服务端或放宽协议门槛。

## 本地检查

Python 3.11+，仅标准库；使用合成样本和模拟 API，不需要真实 Secrets：

```sh
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
actionlint .github/workflows/android.yml
```

测试涵盖 master 前进及单次解析、固定 SHA 检出、其他 ref/版本覆盖拒绝、pubspec 非法/重复版本、版本倒退、双平台来源或版本错配、签名/安装身份/架构检查、禁止覆盖和上传失败不推广 latest。脚本测试与静态检查不等于产品编译、安装兼容性或线上发布验证。

当前设计与验证记录见 [master/源码版本简化计划](docs/plans/2026-10-17-master-version-automation.md)。更早计划仅为历史记录，已由本说明和当前代码取代。


### 正式首轮失败记录

[39026597285](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39026597285) 的 Windows 工具和源码获取成功，依赖解析成功，但导航检查命令立即非零退出，未进入 Windows 应用编译。原始私有输出仍被抑制，确切启动失败原因尚未确认。第二次固定请求绑定已验证 Flutter SDK 内的 Dart.exe，并增加仅数字退出码和固定分类的安全诊断；不关闭导航检查、不降低验包门槛、不声称首轮通过。发布仍须两平台齐备。

第二轮 [39027117454](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39027117454) 两平台编译、打包和包身份检查成功，Windows 导航/codegen 通过；PATH 诊断已指向 SDK 内 Dart，因此首轮启动失败原因仍未证实。两个独立 verifier 均在包检查后被输出名 `apk_sha256` / `installer_sha256` 的旧字母正则阻挡。已改为精确六个输出名 allowlist，并保留注入检查；66项测试与静态检查通过。第三次固定请求重新构建并验证同源双平台后才可发布，前两次均未发布。
