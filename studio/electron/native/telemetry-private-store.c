/* Read-only Windows owner/DACL check. No content, output, settings or network. */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <aclapi.h>
#include <wchar.h>

static BOOL private_path(const wchar_t *path, BOOL directory, PSID user) {
    HANDLE file = CreateFileW(path, READ_CONTROL, FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
    PSECURITY_DESCRIPTOR security = NULL;
    PSID owner = NULL;
    PACL acl = NULL;
    BY_HANDLE_FILE_INFORMATION info;
    BOOL accepted = FALSE;
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    if (!GetFileInformationByHandle(file, &info) ||
        (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) ||
        !!(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != !!directory ||
        (!directory && (info.nNumberOfLinks != 1 || info.nFileSizeHigh != 0 || info.nFileSizeLow > 98304))) goto done;
    if (GetSecurityInfo(file, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        &owner, NULL, &acl, NULL, &security) != ERROR_SUCCESS || !owner || !acl ||
        !IsValidSid(owner) || !EqualSid(owner, user) || !IsValidAcl(acl) ||
        acl->AceCount < 1 || acl->AceCount > 1024) goto done;
    for (DWORD index = 0; index < acl->AceCount; index++) {
        void *entry = NULL;
        if (!GetAce(acl, index, &entry)) goto done;
        ACE_HEADER *header = (ACE_HEADER *)entry;
        if (!directory && (header->AceFlags & INHERIT_ONLY_ACE)) continue;
        if (header->AceType == ACCESS_DENIED_ACE_TYPE) continue;
        if (header->AceType != ACCESS_ALLOWED_ACE_TYPE || header->AceSize < sizeof(ACCESS_ALLOWED_ACE)) goto done;
        PSID sid = (PSID)&((ACCESS_ALLOWED_ACE *)entry)->SidStart;
        if (!IsValidSid(sid) || !EqualSid(sid, user)) goto done;
    }
    accepted = TRUE;
done:
    if (security) LocalFree(security);
    CloseHandle(file);
    return accepted;
}

int wmain(int argc, wchar_t **argv) {
    HANDLE token = NULL;
    DWORD size = 0;
    TOKEN_USER *user = NULL;
    int result = 1;
    if (argc != 3 || wcslen(argv[1]) > 32760 || wcslen(argv[2]) > 32760) return 1;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 1;
    GetTokenInformation(token, TokenUser, NULL, 0, &size);
    if (size < sizeof(TOKEN_USER) || size > 65536) goto done;
    user = (TOKEN_USER *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, size);
    if (!user || !GetTokenInformation(token, TokenUser, user, size, &size)) goto done;
    if (private_path(argv[1], TRUE, user->User.Sid) && private_path(argv[2], FALSE, user->User.Sid)) result = 0;
done:
    if (user) HeapFree(GetProcessHeap(), 0, user);
    CloseHandle(token);
    return result;
}
