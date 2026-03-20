import Foundation

struct GenericCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?

    init(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

extension KeyedDecodingContainer {
    func decodeLossyString(forKey key: Key) -> String {
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return String(value)
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return String(value)
        }
        return ""
    }

    func decodeLossyInt(forKey key: Key, default defaultValue: Int = 0) -> Int {
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return Int(value.trimmingCharacters(in: .whitespacesAndNewlines)) ?? defaultValue
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return Int(value)
        }
        return defaultValue
    }

    func decodeLossyBool(forKey key: Key, default defaultValue: Bool = false) -> Bool {
        decodeLossyOptionalBool(forKey: key) ?? defaultValue
    }

    func decodeLossyOptionalBool(forKey key: Key) -> Bool? {
        guard contains(key) else { return nil }
        if let value = try? decodeIfPresent(Bool.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value != 0
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "true", "1", "yes", "y", "on":
                return true
            case "false", "0", "no", "n", "off":
                return false
            default:
                return nil
            }
        }
        return nil
    }

    func decodeLossyStringArray(forKey key: Key) -> [String] {
        if let values = try? decodeIfPresent([String].self, forKey: key) {
            return values
        }
        if let values = try? decodeIfPresent([Int].self, forKey: key) {
            return values.map(String.init)
        }
        return []
    }

    func decodeLossyStringDictionary(forKey key: Key) -> [String: String] {
        if let values = try? decodeIfPresent([String: String].self, forKey: key) {
            return values
        }
        return [:]
    }

    func decodeLossyObject<T: Decodable>(forKey key: Key, default defaultValue: T) -> T {
        if let value = try? decodeIfPresent(T.self, forKey: key) {
            return value
        }
        return defaultValue
    }

    func decodeLossyArray<T: Decodable>(forKey key: Key) -> [T] {
        if let values = try? decodeIfPresent([T].self, forKey: key) {
            return values
        }
        return []
    }
}
