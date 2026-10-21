// Platform asset export of the user-approved artwork; no generative redesign.
import AppKit

let root = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : FileManager.default.currentDirectoryPath)
let source = root.appendingPathComponent("assets/translator-icon-c1-refined-preview.png")
guard let image = NSImage(contentsOf: source), image.size == NSSize(width: 1254, height: 1254) else {
    fatalError("Expected the approved 1254px icon master")
}
let files = FileManager.default
let work = files.temporaryDirectory.appendingPathComponent("translator-icon-\(UUID().uuidString)")
let iconset = work.appendingPathComponent("AppIcon.iconset")
try files.createDirectory(at: iconset, withIntermediateDirectories: true)
defer { try? files.removeItem(at: work) }

func png(_ size: Int) -> Data {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    bitmap.size = NSSize(width: size, height: size)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    NSGraphicsContext.current?.imageInterpolation = .high
    let factor = CGFloat(size) / 1024
    let tile = NSRect(x: 64 * factor, y: 64 * factor, width: 896 * factor, height: 896 * factor)
    // Clip only the noisy exterior of the approved tile during platform export.
    NSBezierPath(roundedRect: tile, xRadius: 200 * factor, yRadius: 200 * factor).addClip()
    image.draw(in: tile, from: NSRect(x: 56, y: 60, width: 1144, height: 1130),
               operation: .copy, fraction: 1, respectFlipped: false, hints: nil)
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using: .png, properties: [:])!
}

var images: [Int: Data] = [:]
for size in [16, 32, 48, 64, 128, 180, 256, 512, 1024] { images[size] = png(size) }
for size in [16, 32, 128, 256, 512] {
    try images[size]!.write(to: iconset.appendingPathComponent("icon_\(size)x\(size).png"))
    try images[size * 2]!.write(to: iconset.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
process.arguments = ["-c", "icns", iconset.path, "-o", root.appendingPathComponent("assets/AppIcon.icns").path]
try process.run()
process.waitUntilExit()
guard process.terminationStatus == 0 else { fatalError("iconutil failed") }

func littleEndian(_ value: Int, _ bytes: Int, into data: inout Data) {
    for shift in 0..<bytes { data.append(UInt8((value >> (8 * shift)) & 255)) }
}
func ico(_ sizes: [Int]) -> Data {
    var result = Data()
    littleEndian(0, 2, into: &result); littleEndian(1, 2, into: &result)
    littleEndian(sizes.count, 2, into: &result)
    var offset = 6 + 16 * sizes.count
    for size in sizes {
        let payload = images[size]!
        result.append(contentsOf: [UInt8(size % 256), UInt8(size % 256), 0, 0])
        littleEndian(1, 2, into: &result); littleEndian(32, 2, into: &result)
        littleEndian(payload.count, 4, into: &result); littleEndian(offset, 4, into: &result)
        offset += payload.count
    }
    for size in sizes { result.append(images[size]!) }
    return result
}
let web = root.appendingPathComponent("web/public")
try files.createDirectory(at: web, withIntermediateDirectories: true)
try images[1024]!.write(to: root.appendingPathComponent("assets/icon.png"))
try ico([16, 32, 48]).write(to: web.appendingPathComponent("favicon.ico"))
try images[256]!.write(to: web.appendingPathComponent("brand-icon.png"))
try images[180]!.write(to: web.appendingPathComponent("apple-touch-icon.png"))
print("Exported selected icon to PNG, ICNS and web assets")
