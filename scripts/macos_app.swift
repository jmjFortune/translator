import AppKit
import WebKit
import UniformTypeIdentifiers

struct LauncherConfig: Decodable {
    let mode: String?
    let projectRoot: String
    let python: String
}

@MainActor
final class DesktopApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backend: Process?
    private var serverURL: URL?
    private var readyFile: URL?
    private var pollTimer: Timer?
    private var stopSignal: DispatchSourceSignal?
    private var attempts = 0
    private var downloads: [ObjectIdentifier: (URL, URL)] = [:]
    private let logs = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/pdf2zh")

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Finder and command-line launches share the same graceful cleanup path.
        signal(SIGTERM, SIG_IGN)
        stopSignal = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        stopSignal?.setEventHandler { NSApp.terminate(nil) }
        stopSignal?.resume()
        NSApp.setActivationPolicy(.regular)
        if let icon = Bundle.main.url(forResource: "TranslatorIcon", withExtension: "icns") {
            NSApp.applicationIconImage = NSImage(contentsOf: icon)
        }
        let menu = NSMenu()
        let appMenu = NSMenu()
        let root = NSMenuItem()
        root.submenu = appMenu
        menu.addItem(root)
        appMenu.addItem(withTitle: "关于 translator", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 translator", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let edit = NSMenuItem()
        edit.title = "编辑"
        edit.submenu = NSMenu(title: "编辑")
        edit.submenu?.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.submenu?.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.submenu?.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.submenu?.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        menu.addItem(edit)
        NSApp.mainMenu = menu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "translator — Academic Translation"
        window.minSize = NSSize(width: 1050, height: 650)
        webView = WKWebView(frame: .zero)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.loadHTMLString("<p style='font:16px -apple-system;padding:40px'>正在启动 translator…</p>", baseURL: nil)

        do {
            let configURL = Bundle.main.url(forResource: "launcher", withExtension: "json")!
            let config = try JSONDecoder().decode(LauncherConfig.self, from: Data(contentsOf: configURL))
            let bundled = config.mode == "bundled"
            let resources = Bundle.main.resourceURL!
            let project = bundled ? resources.appendingPathComponent(config.projectRoot).path : config.projectRoot
            let python = bundled ? resources.appendingPathComponent(config.python).path : config.python
            guard FileManager.default.fileExists(atPath: project + "/web/out/index.html"),
                  FileManager.default.isExecutableFile(atPath: python) else {
                fail("应用文件不完整，请重新安装 translator。")
                return
            }
            if bundled {
                startBackend(project: project, python: python, bundled: true)
            } else {
                checkServer(URL(string: "http://127.0.0.1:8000")!) { available in
                    if available { self.load(URL(string: "http://127.0.0.1:8000")!) }
                    else { self.startBackend(project: project, python: python, bundled: false) }
                }
            }
        } catch { fail(error.localizedDescription) }
    }

    private func checkServer(_ url: URL, completion: @escaping (Bool) -> Void) {
        var request = URLRequest(url: url.appendingPathComponent("api/health"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let info = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            let available = (response as? HTTPURLResponse)?.statusCode == 200
                && info?["name"] as? String == "translator API" && info?["mock"] as? Bool == false
            DispatchQueue.main.async { completion(available) }
        }.resume()
    }

    private func startBackend(project: String, python: String, bundled: Bool) {
        do {
            try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
            let logURL = logs.appendingPathComponent("desktop-backend.log")
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil, attributes: [.posixPermissions: 0o600])
            }
            let log = try FileHandle(forWritingTo: logURL)
            log.seekToEndOfFile()
            readyFile = logs.appendingPathComponent("ready-\(UUID().uuidString).json")
            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = ["-B", "-m", "server.desktop", "--ready-file", readyFile!.path]
            process.currentDirectoryURL = URL(fileURLWithPath: project)
            var environment = ProcessInfo.processInfo.environment
            environment.removeValue(forKey: "PYTHONHOME")
            environment.removeValue(forKey: "PYTHONPATH")
            environment["PDF2ZH_MOCK"] = "0"
            environment["PYTHONUNBUFFERED"] = "1"
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONNOUSERSITE"] = "1"
            if bundled {
                environment["PATH"] = URL(fileURLWithPath: python).deletingLastPathComponent().path + ":/usr/bin:/bin:/usr/sbin:/sbin"
                let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/translator")
                if environment["PDF2ZH_DATA_DIR"] == nil {
                    environment["PDF2ZH_DATA_DIR"] = support.appendingPathComponent("pdf2zh_files").path
                }
                environment["PDF2ZH_ASSET_SOURCE"] = Bundle.main.resourceURL!.appendingPathComponent("engine-assets.zip").path
            }
            process.environment = environment
            process.standardOutput = log
            process.standardError = log
            try process.run()
            backend = process
            pollTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { _ in
                Task { @MainActor in self.pollBackend() }
            }
        } catch { fail(error.localizedDescription) }
    }

    private func pollBackend() {
        attempts += 1
        guard backend?.isRunning == true, attempts < 600 else {
            pollTimer?.invalidate()
            fail("后端启动失败。请查看 \(logs.appendingPathComponent("desktop-backend.log").path)")
            return
        }
        guard let file = readyFile, let data = try? Data(contentsOf: file),
              let info = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let address = info["url"] as? String, let url = URL(string: address) else { return }
        checkServer(url) { available in if available && self.serverURL == nil { self.load(url) } }
    }

    private func load(_ url: URL) {
        pollTimer?.invalidate()
        serverURL = url
        record("Connecting to \(url.absoluteString); owned backend: \(backend != nil)")
        webView.load(URLRequest(url: url))
    }

    private func record(_ message: String) {
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let file = logs.appendingPathComponent("desktop-launcher.log")
        if !FileManager.default.fileExists(atPath: file.path) {
            FileManager.default.createFile(atPath: file.path, contents: nil, attributes: [.posixPermissions: 0o600])
        }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        handle.seekToEndOfFile()
        handle.write(Data("\(Date()): \(message)\n".utf8))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let serverURL, webView.url?.host == serverURL.host,
              webView.url?.port == serverURL.port else { return }
        record("WebKit finished loading the frontend")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        fail("页面加载失败：\(error.localizedDescription)")
    }

    private func fail(_ message: String) {
        record(message)
        let alert = NSAlert()
        alert.messageText = "translator"
        alert.informativeText = message
        alert.runModal()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        if let process = backend, process.isRunning {
            process.terminate()
            let deadline = Date().addingTimeInterval(3)
            while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if process.isRunning { kill(-process.processIdentifier, SIGKILL); kill(process.processIdentifier, SIGKILL) }
        }
        // A translation child can outlive its server parent; this group is ours.
        if let process = backend { kill(-process.processIdentifier, SIGKILL) }
        if let readyFile { try? FileManager.default.removeItem(at: readyFile) }
        record("Launcher exited; owned backend cleaned up")
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.pdf]
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.urls : nil) }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "确认")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload { decisionHandler(.download); return }
        if action.navigationType == .linkActivated, let url = action.request.url,
           url.host != serverURL?.host || url.port != serverURL?.port {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        decisionHandler(disposition.lowercased().hasPrefix("attachment") || !response.canShowMIMEType ? .download : .allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.beginSheetModal(for: window) { result in
            guard result == .OK, let target = panel.url else { completionHandler(nil); return }
            let staging = target.deletingLastPathComponent().appendingPathComponent(".translator-\(UUID().uuidString).download")
            self.downloads[ObjectIdentifier(download)] = (staging, target)
            completionHandler(staging)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let (staging, target) = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        do {
            if FileManager.default.fileExists(atPath: target.path) {
                _ = try FileManager.default.replaceItemAt(target, withItemAt: staging)
            } else { try FileManager.default.moveItem(at: staging, to: target) }
        } catch { fail("文件保存失败：\(error.localizedDescription)") }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let (staging, _) = downloads.removeValue(forKey: ObjectIdentifier(download)) { try? FileManager.default.removeItem(at: staging) }
        fail("下载失败：\(error.localizedDescription)")
    }
}

@main
struct Main {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = DesktopApp()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
