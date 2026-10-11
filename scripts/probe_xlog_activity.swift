// Read only the logger's timing events, never account settings or credentials.
import Foundation

let defaults = UserDefaults(suiteName: "com.oliverbross.OM0RXXLog")!
guard let data = defaults.data(forKey: "OM0RX-xLog.operatorActivity.v1"),
      let events = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
    fatalError("No persisted xLog timing events")
}
let recent = events.filter { ($0["kind"] as? String) == "tune" }.prefix(6)
let output = try JSONSerialization.data(withJSONObject: Array(recent), options: [.prettyPrinted, .sortedKeys])
print(String(decoding: output, as: UTF8.self))
