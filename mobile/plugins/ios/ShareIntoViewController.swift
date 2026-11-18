import UIKit
import UniformTypeIdentifiers

final class ShareIntoViewController: UIViewController {
  private let preview = UITextView()
  private let status = UILabel()
  private let save = UIButton(type: .system)
  private let cancel = UIButton(type: .system)
  private var incoming: String?

  override func viewDidLoad() {
    super.viewDidLoad()
    view.backgroundColor = .systemBackground
    status.text = "Входящий материал"
    status.font = .preferredFont(forTextStyle: .headline)
    status.adjustsFontForContentSizeCategory = true
    status.numberOfLines = 0
    preview.isEditable = false
    preview.adjustsFontForContentSizeCategory = true
    preview.font = .preferredFont(forTextStyle: .body)
    preview.accessibilityLabel = "Принятый материал"
    save.setTitle("Сохранить черновик", for: .normal)
    save.isEnabled = false
    save.addTarget(self, action: #selector(saveDraft), for: .touchUpInside)
    cancel.setTitle("Отмена", for: .normal)
    cancel.addTarget(self, action: #selector(close), for: .touchUpInside)

    let stack = UIStackView(arrangedSubviews: [status, preview, save, cancel])
    stack.axis = .vertical
    stack.spacing = 12
    stack.translatesAutoresizingMaskIntoConstraints = false
    view.addSubview(stack)
    let guide = view.safeAreaLayoutGuide
    NSLayoutConstraint.activate([
      stack.topAnchor.constraint(equalTo: guide.topAnchor, constant: 20),
      stack.bottomAnchor.constraint(equalTo: guide.bottomAnchor, constant: -20),
      stack.leadingAnchor.constraint(equalTo: guide.leadingAnchor, constant: 20),
      stack.trailingAnchor.constraint(equalTo: guide.trailingAnchor, constant: -20),
      save.heightAnchor.constraint(greaterThanOrEqualToConstant: 44),
      cancel.heightAnchor.constraint(greaterThanOrEqualToConstant: 44)
    ])
    loadShare()
  }

  private func loadShare() {
    let items = extensionContext?.inputItems.compactMap { $0 as? NSExtensionItem } ?? []
    let attachments = items.flatMap { $0.attachments ?? [] }
    guard attachments.count == 1, let provider = attachments.first else {
      if attachments.isEmpty && items.count == 1 {
        display(items.first?.attributedContentText?.string)
      } else {
        display(nil)
      }
      return
    }
    let type = provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) ? UTType.url : UTType.plainText
    guard provider.hasItemConformingToTypeIdentifier(type.identifier) else { display(nil); return }
    provider.loadItem(forTypeIdentifier: type.identifier, options: nil) { [weak self] value, _ in
      let text = (value as? URL)?.absoluteString ?? (value as? String)
      DispatchQueue.main.async { self?.display(text) }
    }
  }

  private func display(_ input: String?) {
    guard let text = input?.trimmingCharacters(in: .whitespacesAndNewlines),
          !text.isEmpty, text.utf16.count <= 20_000,
          URLComponents(string: text)?.scheme?.lowercased() != "file" else {
      status.text = "Нужна одна ссылка или текст до 20 000 символов."
      return
    }
    incoming = text
    preview.text = text
    save.isEnabled = true
  }

  @objc private func saveDraft() {
    guard let value = incoming else { return }
    save.isEnabled = false
    do {
      let files = FileManager.default
      guard let group = Bundle.main.object(forInfoDictionaryKey: "AppGroupId") as? String,
            let groupURL = files.containerURL(forSecurityApplicationGroupIdentifier: group) else {
        throw CocoaError(.fileWriteNoPermission)
      }
      var directory = groupURL.appendingPathComponent("TeleiosisInbox", isDirectory: true)
      try files.createDirectory(at: directory, withIntermediateDirectories: true,
                                attributes: [.protectionKey: FileProtectionType.complete])
      var resources = URLResourceValues()
      resources.isExcludedFromBackup = true
      try directory.setResourceValues(resources)
      guard try files.contentsOfDirectory(atPath: directory.path).count < 100 else {
        status.text = "Входящие заполнены. Откройте Телеосис и обработайте черновики."
        return
      }
      let file = directory.appendingPathComponent(UUID().uuidString.lowercased() + ".txt")
      try Data(value.utf8).write(to: file, options: [.atomic, .completeFileProtection])
      extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    } catch {
      status.text = "Не удалось сохранить черновик. Разблокируйте устройство и повторите."
      save.isEnabled = true
    }
  }

  @objc private func close() {
    extensionContext?.cancelRequest(withError: CocoaError(.userCancelled))
  }
}
