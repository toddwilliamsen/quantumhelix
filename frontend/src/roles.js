/**
 * Role vocabulary shared by the account and administration screens.
 * Mirrors the roles enforced in routes.py.
 */

export const MIN_PASSWORD_LENGTH = 10;

export const ROLE_LABELS = {
  SUPER_ADMIN: 'Super Admin',
  TENANT_ADMIN: 'Tenant Admin',
  TIER_2: 'Tier 2 Analyst',
  TIER_1: 'Tier 1 Analyst',
  READ_ONLY: 'Read Only',
};

export const ADMIN_ROLES = ['SUPER_ADMIN', 'TENANT_ADMIN'];

export function isAdmin(role) {
  return ADMIN_ROLES.includes(role);
}

export function canMutateAlerts(role) {
  return role && role !== 'READ_ONLY';
}

/** Roles an admin may grant. Tenant admins may not create or promote admins. */
export function assignableRoles(actorRole) {
  return actorRole === 'SUPER_ADMIN'
    ? ['SUPER_ADMIN', 'TENANT_ADMIN', 'TIER_2', 'TIER_1', 'READ_ONLY']
    : ['TIER_2', 'TIER_1', 'READ_ONLY'];
}
