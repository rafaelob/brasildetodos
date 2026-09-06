// SPDX-License-Identifier: AGPL-3.0-or-later
// Client affordances only. The authenticated API remains the authority.
export const TASK_STATES = ['open','in_progress','submitted','accepted','changes_requested','cancelled','evidence_unavailable'];
export function taskActions(task, owner = false, active = true) {
  if (!active || !task || !TASK_STATES.includes(task.state)) return [];
  const actions = [];
  if (task.state === 'open') actions.push('claim');
  if (task.assigned_to_me && ['in_progress','changes_requested'].includes(task.state)) actions.push('release','submit');
  if (task.can_review && !task.assigned_to_me && task.state === 'submitted' && task.observation) actions.push('accept','request_changes');
  if ((owner || task.assigned_to_me) && ['accepted','submitted','changes_requested'].includes(task.state)) actions.push('reopen');
  if ((owner || task.created_by_me) && task.state !== 'cancelled') actions.push('cancel');
  return actions;
}
export function ownObservations(rows, placeId) {
  if (!Array.isArray(rows)) return [];
  return rows.filter(row => row && row.place_id === placeId && ['pending','approved'].includes(row.status)
    && row.observation && typeof row.observation.body === 'string' && !row.observation.erased);
}
export function groupFailure(error) {
  const status = /HTTP (\d{3})/.exec(String(error))?.[1];
  return ({401:'loginRequired',403:'forbidden',404:'unavailable',409:'conflict',422:'invalid',429:'rateLimited'})[status] || 'failure';
}
export function validToken(value) { return typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value); }
export function taskPage(page, total) {
  if (!Number.isSafeInteger(total) || total < 0) throw new Error('invalid_task_total');
  const last = Math.max(1,Math.ceil(total/20));
  return Math.max(1,Math.min(last,Number.isSafeInteger(page)?page:1));
}
