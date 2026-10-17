# Android 构建基础设施计划

> 历史计划：已由 `2026-10-17-stable-android-windows.md` 取代。用户随后批准增加 Windows 并复用原正式 latest 更新机制。

- 新建公开 `jsdfhasuh/emosonic-build`，仅存放新编写的脚本、配置和测试。
- 固定私有来源 `jsdfhasuh/emosonic`，目标 `jsdfhasuh/emosonic-releases`。
- 审查基线：`master` = `f5d1dec2c8d5b90def0fd23c1b4a1173a7e9e1d1`；源码版本 `1.0.6+22`，已发布 `v1.0.6+23`。
- 手动 main 分支运行；输入 ref 解析为 SHA，并仅接受 policy 中经过人工审查的 SHA。禁止任意命令和任意仓库输入。
- 隔离准备、构建、独立验证、发布四个 job。发布权限只进入发布最后一步。缺凭据失败，不使用 debug 签名。
- 固定原包名、原证书指纹、Flutter 3.41.2、Java 17、通用 APK 的三种 ABI。
- 单独 Android release 必须为 prerelease 且不改变 latest，使用 `android-vVERSION+BUILD` 标签，避免旧 CI 使用的 `vVERSION+BUILD` 标签。现有更新器只查询 latest，故新包仅供手动安装。
- 版本不得低于源码版本；相对于所有已发布版本与标签，语义版本不能降低且 build number 必须严格增加。不得更新已存在 Release 或覆盖资产。
- 本次只运行基础设施静态/负例测试；真实 APK 构建及发布必须等用户配置 Secrets 并确认具体版本。
