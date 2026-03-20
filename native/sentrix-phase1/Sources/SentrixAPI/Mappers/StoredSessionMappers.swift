import Foundation
import SentrixCore

enum StoredSessionMapper {
    static func map(_ dto: StoredSessionUserDTO) -> StoredSessionUserSummary {
        StoredSessionUserSummary(
            id: dto.id,
            username: dto.username,
            loginID: dto.loginID,
            fullName: dto.fullName,
            role: dto.role,
            group: dto.group,
            siteID: dto.siteID,
            siteCode: dto.siteCode,
            siteName: dto.siteName,
            tenantID: dto.tenantID,
            location: dto.location,
            status: dto.status,
            linkedEmployeeID: dto.linkedEmployeeID,
            employeeID: dto.employeeID
        )
    }

    static func map(_ user: StoredSessionUserSummary) -> StoredSessionUserDTO {
        StoredSessionUserDTO(
            id: user.id,
            username: user.username,
            loginID: user.loginID,
            fullName: user.fullName,
            role: user.role,
            group: user.group,
            siteID: user.siteID,
            siteCode: user.siteCode,
            siteName: user.siteName,
            tenantID: user.tenantID,
            location: user.location,
            status: user.status,
            linkedEmployeeID: user.linkedEmployeeID,
            employeeID: user.employeeID
        )
    }
}
