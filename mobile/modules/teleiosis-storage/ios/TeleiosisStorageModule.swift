import ExpoModulesCore
import Foundation

public final class TeleiosisStorageModule: Module {
  public func definition() -> ModuleDefinition {
    Name("TeleiosisStorage")

    AsyncFunction("databaseDirectory") { () -> String in
      let files = FileManager.default
      let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                  appropriateFor: nil, create: true)
      var directory = support.appendingPathComponent("Teleiosis", isDirectory: true)
      let protection: [FileAttributeKey: Any] = [.protectionKey: FileProtectionType.complete]
      try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: protection)
      try files.setAttributes(protection, ofItemAtPath: directory.path)
      var resource = URLResourceValues()
      resource.isExcludedFromBackup = true
      try directory.setResourceValues(resource)
      let database = directory.appendingPathComponent("teleiosis.db")
      if !files.fileExists(atPath: database.path),
         !files.createFile(atPath: database.path, contents: nil, attributes: protection) {
        throw CocoaError(.fileWriteUnknown)
      }
      return directory.path
    }

    AsyncFunction("pendingShares") { () -> [[String: String]] in
      guard let directory = self.inbox(), FileManager.default.fileExists(atPath: directory.path) else { return [] }
      let entries = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.fileSizeKey])
      return try entries.compactMap { file in
        let id = file.deletingPathExtension().lastPathComponent
        guard file.pathExtension == "txt", UUID(uuidString: id) != nil else { return nil }
        guard let size = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 80_000 else { return nil }
        return ["id": id, "value": try String(contentsOf: file, encoding: .utf8)]
      }
    }

    AsyncFunction("removeShare") { (id: String) in
      guard UUID(uuidString: id)?.uuidString.lowercased() == id, let directory = self.inbox() else { return }
      let file = directory.appendingPathComponent(id + ".txt")
      do { try FileManager.default.removeItem(at: file) }
      catch let error as CocoaError where error.code == .fileNoSuchFile { }
    }
  }

  private func inbox() -> URL? {
    guard let group = Bundle.main.object(forInfoDictionaryKey: "ExpoShareIntoAppGroupId") as? String else { return nil }
    return FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)?
      .appendingPathComponent("TeleiosisInbox", isDirectory: true)
  }
}
