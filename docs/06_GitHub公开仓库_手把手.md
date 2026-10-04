# 把本仓库推到 GitHub 公开仓库（手把手）

> 你不需要懂 Git。整套事情拆开看只有三块：
> **①在 GitHub 网站上开一个空仓库 → ②把它的网址交给下面的脚本 → ③在弹出的窗口里登录一次**。
> 剩下的上传动作由脚本做。全程大约 3 分钟。

---

## 零、开始前先知道一件事（很重要）

**推上去 = 全世界可见。** 我已经替你检查过这个仓库里的内容：

- 42 个文件，不含任何 API Key、不含 `.env`、不含私钥（已对全部历史提交做过扫描）；
- 唯一的 <Key 占位符> 是文档里写给人看的示例，不是真钥匙；
- 体积最大的文件是两张 PNG（约 390 KB、246 KB）和一份裁决流水 JSON（255 KB），都在 GitHub 的限制内。

但是有一样东西你要自己决定：**commit 上会显示你的邮箱** `2148043455@qq.com`。
如果介意 QQ 邮箱被公开，先做下面的「五、隐私开关」那一节，再做第一节。

---

## 一、在 GitHub 上开一个空仓库（网页操作，1 分钟）

1. 打开 https://github.com/ ，右上角登录（没有账号就注册一个，免费）。
2. 点右上角头像旁边的 **+** 号 → 选 **New repository**（新建仓库）。
3. 按下图填：
   - **Repository name**（仓库名）：建议 `agi-verilog-lab`
   - **Description**（简介，可选）：`AGH 驱动的数字逻辑生成-验证-修复闭环`
   - **Public**（公开）← **一定要选这个**，Private 不算公开发布
   - 下面三个勾选框 **全部不要勾**：
     - Add a README file —— 不要勾
     - Add .gitignore —— 不要勾
     - Choose a license —— 暂时不勾（我们本地已经有了 .gitignore，勾了会打架）
4. 点绿色按钮 **Create repository**。
5. 建好后，页面会给你一个网址，长这样：

```
https://github.com/<你的用户名>/agi-verilog-lab.git
```

页面上有个 **HTTPS** 按钮（默认就是 HTTPS，别选 SSH）。**把这一整行复制下来**，下一步要用。

> 如果你不小心勾了 README，页面会变成有文件的仓库，推送会被拒绝。
> 解决办法：把那个仓库删掉重建（Settings → 最下面 Danger Zone → Delete repository）。

---

## 二、两种推送方式，选一个

### 方式 A：双击脚本（推荐，你什么都不用记）

到这个文件夹里：

```
C:\Users\liumi\WorkBuddy\2026-10-02-20-04-02\agi-verilog-lab
```

双击 **`push-to-github.bat`**。黑窗口会问你一行字：

```
Paste repository URL:
```

把第一步复制的那行网址粘进去（黑窗口里用鼠标右键 = 粘贴），按回车。

> 如果没看到这个文件，或者双击后一闪而过，就用方式 B。

### 方式 B：让我来推（你只负责登录）

直接把那行网址发给我，说一句「推这个」，我来执行。下面的内容你就不用管了。

---

## 三、第一次推送时登录 GitHub（会弹窗）

无论哪种方式，第一次推送一定会卡在登录这步，这是正常的：

- **弹浏览器**：GitHub 登录页 → 输入账号密码 → 绿色按钮 **Authorize git-ecosystem**（授权）→ 看到 "Success" 就关掉窗口；
- **或者弹一个小输入框**：用户名填你的 GitHub 用户名 / 或者邮箱，密码栏**填的不是登录密码**，而是下面第四节说的令牌。

登录成功后，命令行自己会继续跑，看到 `Branch 'main' set up to track...` 就是成功了。

> 本机装的是完整版 Git for Windows（2.55），自带凭据管理器。
> 所以**优先会走浏览器授权**这条路，你不用手动去生成任何东西。

---

## 四、万一弹的是「要密码」而不是浏览器（备用方案）

说明这台机器的浏览器授权没触发。那就用「个人令牌」代替密码，做一次就好：

1. GitHub 右上角头像 → **Settings**
2. 左侧最下面 **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. 右上角 **Generate new token (classic)**
4. Note 随便填（比如 `vlab`）；Expiration 选 **90 days**
5. 勾选 **`repo`**（勾这一项，它下面的一堆子项会自动勾上）
6. 页面最下面 **Generate token**
7. **立刻复制那串 ghp_ 开头的字符**（关掉页面就再也看不到了，只能重新生成）

然后回到黑窗口：
- Username（用户名）：你的 GitHub 用户名
- Password（密码）：粘贴这串 `ghp_...`（粘贴时屏幕不显示是正常的，不是卡住了）

> 令牌泄露了怎么办：回到同一个页面点 **Delete** 删掉就行，不影响账号。

---

## 五、隐私开关：不想公开 QQ 邮箱

GitHub 有一个免费的「转发邮箱」可以用：

1. Settings → **Emails** → 勾选 **Keep my email addresses private**
2. 页面上会显示一个形如 `<用户名>@users.noreply.github.com` 的地址，复制它
3. 告诉我把它写进 Git 配置即可，或者自己在 Git Bash 里跑：

```bash
git config --global user.email "<粘贴那个 noreply 地址>"
```

> 注意：这只影响**以后**的提交。已经产生的两个提交里还是旧邮箱 —— 如果那两个提交你也想改，
> 告诉我，我帮你重写历史后重新推送（会改写提交号，必须干净仓库才安全）。

---

## 六、推完之后怎么确认

打开 `https://github.com/<你的用户名>/agi-verilog-lab`，应当看到：

- 绿色 **Public** 标签 ✅
- README.md 的内容渲染在下方 ✅
- 42 个文件，`docs/publish/` 里两张截图能直接点开看 ✅

把**这个页面地址**填到赛事提交表单的「代码仓库地址」栏，再配一张浏览器截图，
「公开发布」这一项就是双保险（主页链接 + 代码仓库）。

---

## 七、常见报错速查

| 报错 | 原因 | 怎么办 |
|---|---|---|
| `repository not found` | 网址抄错，或仓库是 Private | 核对网址；确认仓库是 Public（其实 Private 也能推，只是不满足公开发布要求） |
| `failed to push some refs` | 你在 GitHub 上勾了 README / LICENSE，两边历史不一致 | 回到 GitHub 把仓库删了重建，别勾那三个选项 |
| `Authentication failed` | 令牌没勾 repo，或令牌过期 | 按第四节重生成一个，勾选 repo |
| `Support for password authentication was removed` | 用了登录密码当密码 | 密码栏必须填令牌（第四节），不是账号密码 |
| 中文文件名显示成一串数字 | 不是错误 | Git 只是用八进制转义显示中文，GitHub 网页上是正常的中文 |

---

## 八、完全不用命令行的备选方式

如果你实在不想碰黑窗口：

1. 按第一节建好空仓库
2. 仓库页面上点 **uploading an existing file**（或在开户页底部拖文件区）
3. 把 `agi-verilog-lab` 文件夹里的**文件和文件夹直接拖进去**（GitHub 支持拖文件夹，单次不超过 100 个文件）
4. 下面填一句提交说明 → **Commit changes**

缺点：丢掉提交历史（只剩 1 个 commit），评审看不到你的迭代过程。
建议还是用前面的脚本方式，历史提交本身也是「独立完成」的证据。
