# EmoSonic Android + Windows builder

为私有 `jsdfhasuh/emosonic` 的同一已审查源码提交、同一版本构建正式签名 Android APK 和真实 Windows x64 Inno Setup 安装包，统一发布到公开 [emosonic-releases](https://github.com/jsdfhasuh/emosonic-releases)。本仓库只包含构建基础设施，不包含产品源码、keystore 或 token；不构建 iOS。

**当前状态：本地基础设施测试和静态检查通过，已对现有公开 Windows 安装包做只读解包验证。未实际编译私有产品源码、未运行 Actions、未发布新安装包。真实运行仍等待用户配置 Secrets 和确认版本。**

## 完整复用原应用内更新

现有 Android 和 Windows 都请求 `jsdfhasuh/emosonic-releases/releases/latest`。本流程恢复原标签 `vX.Y.Z+N`，仅在两个平台构建及独立验证均成功、全部资产上传并校验后，才把草稿变成 **正式 Release / latest**。

旧客户端只识别 `vX.Y.Z+N`（也接受无 v 前缀），不会识别 `android-v…`。Android 选择 `.apk`；Windows 选择 `.exe`/`.msi`，优先名称含对应平台词的资产。这里保持原命名及同名 `.sha256` 格式，不需要修改应用更新地址或解析器。

这取代了首版仓库的 Android-only 预发布方案：当前不提供 `publish-prerelease` 模式，也不会复制旧 Windows 安装包冒充新版本。两个平台包必须来自同一次运行的同一 source SHA、同一版本。iOS 不在本轮范围。

## Environment / Secrets 配置

为避免已配置用户重新迁移，保留 `android-build`、`android-release` 名称，只新增 `windows-build`。虽然名称仍叫 `android-release`，它现在负责双平台统一发布。

1. 打开 [Environments](https://github.com/jsdfhasuh/emosonic-build/settings/environments)，创建以下三个环境；Deployment branches and tags **只允许 main**。建议为 `android-release` 开启人工审批，并保护 main，禁止未审查推送和强推。
2. 用户亲自创建两个不同的 [Fine-grained PAT](https://github.com/settings/personal-access-tokens)，设置到期日、Resource owner=`jsdfhasuh`、Only select repositories：

   | Token Secret | 仅选择仓库 | 最小 Repository permissions |
   | --- | --- | --- |
   | `SOURCE_READ_TOKEN` | `jsdfhasuh/emosonic` | Contents: Read-only；Metadata 自动只读 |
   | `RELEASE_WRITE_TOKEN` | `jsdfhasuh/emosonic-releases` | Contents: Read and write；Metadata 自动只读 |

   不需要其他仓库、Actions、Workflows 或管理写权限，不使用拥有全部仓库权限的 classic PAT。新 tag 指向 release 仓库默认分支已有提交，不指向私有源码提交。
3. 用户亲自添加下列 **Environment Secrets**：

   | 环境 | Secrets |
   | --- | --- |
   | `android-build`（原名保留） | `SOURCE_READ_TOKEN`、`DEFAULT_SERVER_URL`、`ANDROID_KEYSTORE_BASE64`、`ANDROID_STORE_PASSWORD`、`ANDROID_KEY_PASSWORD`、`ANDROID_KEY_ALIAS` |
   | `windows-build`（新增） | `SOURCE_READ_TOKEN`、`DEFAULT_SERVER_URL` |
   | `android-release`（原名保留，统一发布） | `RELEASE_WRITE_TOKEN` |

   Windows 环境可由你手动填写与 Android 环境相同的源码只读 PAT 和服务地址。它不需要 Android 签名 Secrets，也不需要新增 Windows 签名 Secret。原公开 Windows 安装包未做 Authenticode 签名，本流程保留该行为；签名策略变化需另行设计。
4. Android 签名四项来自你的**原正式 keystore**及原密码/alias；base64 必须单行。不生成替代签名。两个环境的 `DEFAULT_SERVER_URL` 与原应用保持一致，必须是无账号密码、query、fragment 的 HTTPS URL；Windows 原批处理入口不接受 `%`、引号、空格和 cmd 特殊字符。
5. 保持 Actions 的 `GITHUB_TOKEN` 为只读，并允许工作流列出的完整 SHA Actions。若限制第三方 Actions，需要允许固定提交的 `subosito/flutter-action`。

[Actions Secrets 设置入口](https://github.com/jsdfhasuh/emosonic-build/settings/secrets/actions)。不要把发布 PAT 放到 build 环境；不要在聊天、issue、代码、普通 Variables 或 workflow 输入中粘贴凭据。助手不会创建、读取、复制或代填任何凭据，原仓库 Secrets 也不会自动继承。

`DEFAULT_SERVER_URL` 使用 Secret 避免普通配置/日志公开，但它会进入应用二进制、可被提取，不能当作隐藏凭据。流程不会把它写入公开 manifest 或 Release 文案。

## 手动运行

1. **先确认具体发行版本及 Secrets。** 审查时源码版本 `1.0.6+22`，现有 latest `v1.0.6+23`。新发行不得用这两个 build number。`1.0.6+24` 仅为输入格式示例，并不是已确认版本；每次先重新检查全部 releases/tags。版本名不得降低、build number 必须严格递增；Windows 数字版本资源限制所有四段均不超过 65535。
2. 打开 [Actions 工作流](https://github.com/jsdfhasuh/emosonic-build/actions/workflows/android.yml)，选择 **Android + Windows stable (manual) → Run workflow → main**。为保留原链接，文件名仍为 `android.yml`。
3. `source_ref` 默认固定 SHA `f5d1dec2c8d5b90def0fd23c1b4a1173a7e9e1d1`。流程解析 ref 后只接受 `policy.json` 的已审查 SHA；输入 `master` 若已经移动到未审查提交会失败。更新白名单前须审查产品构建脚本、依赖、签名、安装器和更新行为。Windows 原脚本/模板额外按 Git blob 固定。
4. 首次选择 `build-only`：两个平台都会真实构建及验证，但不创建 Release。两个短期 artifacts 各包含对应安装包、校验和和脱敏 manifest，保留一天；它们属于公开仓库分发面。
5. 下载两包，在已有正式 Android/Windows 安装上验证升级、原配置和数据保留、登录、播放及更新检查。确认发布后，使用 `publish-stable`。它会重建两平台包，所有检查成功后才创建正式 latest。

Android 继续使用 `--build-name`/`--build-number`。Windows 原 `build_windows.bat` 只从 pubspec 读版本，因此仅在临时 runner 源码副本中替换该字段，调用原脚本后恢复；不修改远程产品源码、旧 workflow 或任何功能代码。原脚本的导航检查、build_runner、SMTC 构建修复和原 Inno 模板继续使用。

不要同时让原仓库 workflow 发布相同版本。它仍可能覆盖上传。本仓库 concurrency 只能串行本仓库运行，不能锁住旧仓库；本流程重复检查版本、tag 和 latest 变化，但无法与另一个独立 publisher 实现原子互斥。请统一安排发行；若已存在同名 tag/Release，本流程停止，不接管、不覆盖、不复用旧资产。

## 构建、验证与发布边界

| Job | 行为与权限 |
| --- | --- |
| `prepare` | main 手动触发，解析精确 SHA、检查版本历史；源码只读 token |
| `build` | Linux 构建 Android；原签名 Secrets；无发布 token |
| `build-windows` | Windows 2022 构建 Windows；源码只读 token 仅 fetch 步骤使用，编译步骤只接收服务地址 |
| `verify` | 新 Linux runner，无用户 Secrets，独立检查 APK |
| `verify-windows` | 新 Windows runner，无用户 Secrets，只解包及读取 PE 资源，不运行安装器或应用 |
| `publish` | 新 Linux runner，只读取允许资产及 manifest；发布 token 仅注入最终一步，不执行私有源码、安装器或应用 |

所有公共 checkout 固定本次工作流 SHA，`persist-credentials: false`；私有源码按精确 SHA 静默 fetch，认证只存在于 fetch 子进程环境，不写 git 配置、不打印源码或提交说明。所有 Actions 固定完整提交 SHA，无 pull_request_target、公众评论或自动 push 发布。

Android 固定 `com.example.emosonic` 和原发布证书 SHA-256：`6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`。APK 必须通过 apksigner 验签、版本、非 debug、arm64-v8a/armeabi-v7a/x86_64 三 ABI 检查。

Windows 保留升级 AppId `{779F17F8-DA99-4D5B-A404-E7E2D17C1E65}`、`{localappdata}\Programs\EmoSonic`、`PrivilegesRequired=lowest`、`emosonic.exe` 和 `emosonic_windows_vX.Y.Z+N_setup.exe` 命名。对已审查原脚本/模板复核 Git blob，并用固定哈希的 innounp 只解包：检查安装器身份、完整运行载荷、x64 PE、内含程序数字/字符串版本及非 debug 标志。旧包改名或修改外部 manifest 无法绕过内含程序版本检查。

Windows 工具固定 Inno Setup 6.7.3（原公开包使用 6.7.0，同一 6.7 系列）和 innounp 2.71.2，下载归档及关键可执行文件均校验 SHA-256。编译器通过解包准备，不运行其安装器。[Inno 官方发行](https://github.com/jrsoftware/issrc/releases/tag/is-6_7_3) · [解包器维护者发行](https://github.com/jrathlev/InnoUnpacker-Windows-GUI/releases/tag/ui_2_2_13)。

发布严格只允许六个文件：APK、EXE、各自 `.sha256`、`android-manifest.json`、`windows-manifest.json`。校验来源 repo/SHA、builder SHA、run ID/attempt、版本、平台及包摘要。两份独立 verifier 的摘要都匹配才允许发布。草稿上传后再次核对六份远端摘要/大小及版本并发变化；失败保留草稿，不自动删除、覆盖或重试写入。完成后检查 latest 指向本次 Release。

## 隐私和复现限制

**公开 Actions 无法提供绝对源码保密保证。** 私有工具和编译器 stdout/stderr 被抑制，源树、日志、符号和凭据不上传；只上传通过检查的分发文件。签名临时文件和私有源码会清理。构建源码、插件和依赖仍有 runner 权限，可能主动泄露或把私有内容嵌进安装包；文件扩展名扫描不是完整内容审计。需要强保密时使用私有或隔离构建环境，不要依赖 PAT masking。

固定 Flutter 3.41.2 并核验 SDK SHA，Android 使用 Java 17/build-tools 36.0.0。审查源码没有跟踪 pubspec.lock，故依赖解析尚不保证完全可重复；不擅自更改产品仓库或公开依赖清单。不共享私有源码/依赖构建缓存。

## 本地检查与失败处理

Python 3.11+，测试无需 Python 第三方依赖：

```sh
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
actionlint .github/workflows/android.yml
```

单测使用合成文件/元数据和模拟 API，覆盖版本倒退、旧客户端标签契约、来源错配、缺任一平台、证书/包名/架构/安装身份/内含版本不符、上传失败或远端摘要错配禁止晋升 latest。它们不访问真实 Secrets 或发布 API，也不编译产品。

静态检查、模拟 API 和现有公开安装包的只读验证不等同于真实 SDK 构建及安装升级测试。本次没有执行真实私有源码构建或发布。失败时只打印安全概括错误，请在可信私有环境诊断，不要开启公开 runner debug 或上传原始日志、源树及环境转储。

保留原稳定包，不用旧 build 覆盖。问题版本应停止分发并用更高 build 修复；不要降低设备上的 versionCode。中断草稿由所有者检查处理，不自动删除旧 Release、tag 或资产。Windows/Android 签名、升级 GUID、信任 SHA 与工具更新均需审查。
