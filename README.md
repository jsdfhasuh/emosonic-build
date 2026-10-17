# EmoSonic Android builder

为 `jsdfhasuh/emosonic` 的私有 Flutter 源码构建正式签名 Android APK，并可发布到已有的公开 [emosonic-releases](https://github.com/jsdfhasuh/emosonic-releases)。本仓库公开，但不包含产品源码、keystore 或 token。仅手动触发，不构建 iOS 或 Windows。

**当前状态：基础设施已编写并进行本地测试，未实际运行私有源码编译、未发布新 APK。用户配置全部 Secrets 并确认具体版本后才能运行。**

## 发布兼容性

现有 Android 和 Windows 更新器都只查询 `jsdfhasuh/emosonic-releases/releases/latest`。Android-only Release 若成为 latest，会阻断旧版 Windows 查找更新；复制旧 EXE 到新 tag 又会把旧安装包标成新版本。

因此本流程固定创建 **prerelease，并设置 `make_latest=false`**，使用独立的 `android-vX.Y.Z+BUILD` 标签，保留原 CI 的 `vX.Y.Z+BUILD` 标签空间。新 Android 包供手动下载安装，不会通过现有稳定自动更新入口分发。没有设为 latest 的开关，不会复制或重新标记 Windows 安装包。以后要进入稳定自动更新，应先单独设计同版本多平台发布或渠道变更。

GitHub 官方说明：[Release API 的 prerelease 和 make_latest](https://docs.github.com/en/rest/releases/releases#create-a-release)。

## 一次性配置（由仓库所有者亲自完成）

1. 打开 [Environments 设置](https://github.com/jsdfhasuh/emosonic-build/settings/environments)，创建 `android-build` 和 `android-release`。两者的 Deployment branches and tags 都只允许 `main`。建议为 `android-release` 配置人工审批，并保护 main，禁止未审查的推送、强推和绕过。不要把发布 token 放到 build 环境。
2. 在 GitHub 的 [Fine-grained PAT 设置](https://github.com/settings/personal-access-tokens) 分别创建两个不同的、带到期日的 token。Resource owner 选择 `jsdfhasuh`，Repository access 选择 **Only select repositories**：

   | Secret | 只选择的仓库 | 最小 Repository permissions |
   | --- | --- | --- |
   | `SOURCE_READ_TOKEN` | `jsdfhasuh/emosonic` | Contents: **Read-only**（Metadata 自动只读） |
   | `RELEASE_WRITE_TOKEN` | `jsdfhasuh/emosonic-releases` | Contents: **Read and write**（Metadata 自动只读） |

   不使用拥有全部仓库权限的 classic PAT，不添加管理、组织、Actions 或 Workflows 写权限。发布 tag 指向目标 release 仓库默认分支的现有提交，不指向私有源码提交。

3. 在 `android-build` 环境的 Secrets 添加：

   | 名称 | 值由你亲自填写 |
   | --- | --- |
   | `SOURCE_READ_TOKEN` | 上一步的源码只读 PAT |
   | `ANDROID_KEYSTORE_BASE64` | **现有正式签名 keystore** 的单行严格 base64，不生成替代密钥 |
   | `ANDROID_STORE_PASSWORD` | 原 store password |
   | `ANDROID_KEY_PASSWORD` | 原 key password |
   | `ANDROID_KEY_ALIAS` | 原 key alias |
   | `DEFAULT_SERVER_URL` | 与原构建一致的 HTTPS 服务地址，无账号密码、query 或 fragment |

   这些签名 Secret 名称沿用原 CI。请从你自己的安全备份配置；助手不创建、读取、复制或代填凭据。不要在聊天、issue、代码、Actions 输入或普通 Variables 中粘贴凭据。GitHub 不会把原仓库的 Secrets 自动继承到新仓库。

4. 在 `android-release` 环境中只添加 `RELEASE_WRITE_TOKEN`。可从 [Actions Secrets 设置入口](https://github.com/jsdfhasuh/emosonic-build/settings/secrets/actions) 进入环境管理；推荐使用上述 Environment Secrets，而不是让所有 job 都能引用的同名 Repository Secrets。
5. 保持 Actions 的默认 `GITHUB_TOKEN` 为只读。允许工作流中列出的固定 SHA Actions；仓库设置若限制第三方 Actions，需要允许 `subosito/flutter-action` 的已固定提交。

`DEFAULT_SERVER_URL` 使用 Secret 是为了避免普通配置/日志公开，并不使应用内嵌地址保密：它会进入 APK，可被提取。脚本不会在日志、manifest 或 Release 文案中输出它。若不希望该地址进入公开二进制，先停止运行并确认产品配置方案，不要擅自替换地址。

## 首次运行

1. 先确认版本。审查时源码为 `1.0.6+22`，稳定 latest 为 `v1.0.6+23`。这两个 build number 均不能用于新发布。`1.0.6+24` 仅是格式示例，**并非已经确认的发行版本**；运行前重新核对所有 releases/tags。版本号不得低于源码/历史版本，build number 必须严格大于所有已有 build（包括 prerelease、标签，发布 job 还包括草稿）。
2. 在 [Actions](https://github.com/jsdfhasuh/emosonic-build/actions/workflows/android.yml) 选择 **Android APK (manual) → Run workflow → main**。
3. `source_ref` 默认固定为已审查提交 `f5d1dec2c8d5b90def0fd23c1b4a1173a7e9e1d1`。也可输入解析到该提交的 `master`。流程先解析精确 SHA，再对照 `policy.json` 白名单。分支移动到未审查 SHA 会失败；需先审查新源码的构建脚本、依赖、签名及更新行为，再通过正常代码审查添加 SHA，不能关闭门禁。
4. 填入你确认的 `X.Y.Z+BUILD`，首次选择 `build-only`。流程传入 `--build-name` 和 `--build-number`，不修改源码 pubspec 或产品代码。构建后检查验证 job，并从短期 artifact 下载 APK，在已有正式安装上测试升级、登录、播放及更新检查。
5. 只有明确确认发布时才选择 `publish-prerelease`。它会重新构建同一已审查 SHA，并重新验证所有条件，创建新 draft，上传三个文件、验证远端 digest，再转换为 prerelease。发布中断会保留草稿供人工处理，不会删除/覆盖资产，不会自动恢复或重试写请求。

构建 artifact 仅包含一个通用 APK、同名 `.sha256` 和 `manifest.json`，保留一天；Artifact 是公开仓库的分发面，`build-only` 也会公开这些允许分发的文件。APK 包含 arm64-v8a、armeabi-v7a、x86_64。

不要同时让原仓库的 workflow 发布相同版本。原 workflow 仍可能使用覆盖上传；本流程通过独立标签空间避免直接撞名，但跨仓库并发无法靠本仓库 concurrency 完全互斥。请人为串行安排发行，并为每次发行分配新的 build number。

## 安全与信任边界

- `prepare` 只解析并校验来源，`build` 访问私有源码和原签名，`verify` 在独立 runner 无用户 Secrets 地检查 APK，`publish` 在另一 runner 仅检查文件摘要/元数据并调用目标 Release API。发布 job 不 checkout 私有源码，不执行 APK，不安装私有依赖。写 token 仅出现在发布最后一步。
- 所有 Actions 均固定完整提交 SHA；公开脚本 checkout 固定本次工作流 SHA，`persist-credentials: false`。私有源码用抑制输出的 git fetch 按精确 SHA 获取，授权仅存在于 fetch 子进程环境，不写 git 配置，不抓取子模块，不打印 commit message。
- 固定 Flutter 3.41.2 并复核 SDK 提交，Java 17、Android build-tools 36.0.0；执行 `flutter pub get`、原导航检查和 build_runner。审查提交没有已跟踪的 `pubspec.lock`，因此依赖解析尚不保证可重复；这里不擅自修改产品仓库或生成公开 lockfile。无私有源码/依赖缓存上传。
- 固定包名 `com.example.emosonic`。固定证书 SHA-256：`6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`，从已公开的 `v1.0.6+23` APK 的签名块提取，APK 校验和与公开 `.sha256` 一致。新 APK 必须由 Android `apksigner verify` 验证该证书；拒绝 debug、包名/版本/架构错误、额外文件、源码/凭据/调试文件常见扩展名。
- metadata 区分 source repository/SHA、builder repository/SHA 和本仓库 run URL，不将 builder 的提交冒充产品源码。
- 缺 Secret、API 不可用、未知 tag 格式、版本冲突、源码不受信任或证书不匹配均停止，不回退 debug 签名。

**公开 Actions 日志无法提供绝对源码保密保证。** 脚本抑制编译器和私有工具的 stdout/stderr，不上传构建日志、源树或符号，清理签名文件；但被执行的源码、Gradle 插件和依赖拥有构建 runner 权限，可读取签名文件、联网或主动泄露数据。恶意代码也可把私有信息打包进 APK。扩展名扫描和日志抑制不是沙箱或完整内容审计。只允许审查过的 SHA，并审查依赖/生成器更新；需要强保密时应使用私有或隔离的构建环境。这一点不能通过 PAT 或 Secret masking 消除。

## 验证与维护

Python 3.11+，无需安装 Python 依赖：

```sh
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
actionlint .github/workflows/android.yml
```

测试使用合成 APK/元数据和模拟 API；不会读取真实 Secrets、调用发布 API 或编译产品。静态测试通过不代表真实 SDK 下载、私有依赖安装、签名或 APK 编译已经通过。真实运行失败时日志只给出安全的概括错误，在可信私有环境复现以定位，切勿开启公开 runner debug、上传原始日志或环境转储。

更新 Actions、Flutter、证书或 SHA 白名单需要人工审查。签名变更必须单独制定原用户可升级方案，不能为通过检查直接替换指纹。这里不修改原仓库 workflow、离线功能或产品代码。

回退：保留已发布稳定包和 latest；新 prerelease 有问题时停止分发，使用更高 build number 修复。不要用旧 build 覆盖，也不要降低设备已安装 versionCode。中断草稿需由所有者检查后决定如何处理；不自动删除草稿、标签或已发布二进制。
