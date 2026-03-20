import Foundation

struct StoredSessionUserDTO: Codable {
    let id: Int
    let username: String
    let loginID: String
    let fullName: String
    let role: String
    let group: String
    let siteID: String
    let siteCode: String
    let siteName: String
    let tenantID: String
    let location: String
    let status: String
    let linkedEmployeeID: Int
    let employeeID: Int

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case loginID = "loginId"
        case fullName = "full_name"
        case role
        case group
        case siteID = "site_id"
        case siteCode = "site_code"
        case siteName = "site_name"
        case tenantID = "tenant_id"
        case location
        case status
        case linkedEmployeeID = "linked_employee_id"
        case employeeID = "employee_id"
    }
}
