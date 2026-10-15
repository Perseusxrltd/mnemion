/** Public company metadata and one-use login handoffs; never persist a verifier. */
export type CompanyProvider = { id: string; name: string; issuer: string; session_seconds: number }
export type CompanyConfiguration = { providers: CompanyProvider[]; callback_uri: string | null }
export type CompanyCredentials = { workspace_id: string; provider_id: string; device_name: string; invitation?: string }
export type CompanyStart = { state: string; code_verifier: string; expires_in: number; authorization_url: string; provider: CompanyProvider }
export type CompanyCallback = { type: 'mnemion-company-callback'; state: string; code?: string; error?: string }

