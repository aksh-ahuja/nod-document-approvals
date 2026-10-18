import { test, expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'

const accounts = process.env.NOD_SWAGGER_ACCOUNTS_FILE
  ? JSON.parse(readFileSync(process.env.NOD_SWAGGER_ACCOUNTS_FILE, 'utf8'))
  : { owner: { email: 'jamie@nod.demo', password: 'NodDemo!2026' }, reviewer: { email: 'alex@nod.demo', password: 'NodDemo!2026' }, other: { email: 'sam@nod.demo', password: 'NodDemo!2026' } }


async function execute(page: Page, id: string, path: string, body?: object, parameters: Record<string, string> = {}) {
  const block = page.locator(`#operations-${id}`)
  if (!(await block.getByRole('button', { name: 'Try it out', exact: true }).isVisible())) {
    await block.locator('.opblock-summary').click()
  }
  await block.getByRole('button', { name: 'Try it out', exact: true }).click()
  if (body) await block.locator('textarea.body-param__text').fill(JSON.stringify(body))
  for (const [name, value] of Object.entries(parameters)) {
    await block.locator(`tr[data-param-name="${name}"] input`).fill(value)
  }
  const responsePromise = page.waitForResponse(response => response.url().includes(path) && response.request().method() !== 'OPTIONS')
  await block.getByRole('button', { name: 'Execute', exact: true }).click()
  const response = await responsePromise
  const data = await response.json()
  await expect(block.locator('.responses-inner')).toContainText(String(response.status()))
  await block.getByRole('button', { name: 'Cancel', exact: true }).click()
  return { status: response.status(), body: data }
}

test('Swagger executes login, creates a submission, and reviews it with rotated CSRF', async ({ page }) => {
  await page.goto('/api/docs/')
  await expect(page.getByRole('heading', { name: 'Nod API playground' })).toBeVisible()
  await expect(page.locator('#operations-Authentication-auth_login')).toBeVisible()
  const before = (await page.context().cookies()).find(cookie => cookie.name === 'csrftoken')?.value
  const login = await execute(page, 'Authentication-auth_login', '/auth/login/', accounts.owner)
  expect(login.status).toBe(200)
  const after = (await page.context().cookies()).find(cookie => cookie.name === 'csrftoken')?.value
  expect(after).not.toBe(before)
  const reviewers = await execute(page, 'Submissions-reviewers_list', '/reviewers/list/')
  expect(reviewers.status).toBe(200)
  const alex = reviewers.body.data.find((user: { email: string }) => user.email === accounts.reviewer.email)
  const created = await execute(page, 'Submissions-submissions_create', '/submissions/create/', {
    title: `Swagger review ${randomUUID()}`, content: 'Created using the real Swagger Try it out controls.',
    reviewer_id: alex.id, client_request_id: randomUUID(),
  })
  expect(created.status).toBe(201)
  const id = created.body.data.id
  expect(created.body.data.status).toBe('pending')
  expect((await execute(page, 'Authentication-auth_logout', '/auth/logout/')).status).toBe(200)
  expect((await execute(page, 'Authentication-auth_login', '/auth/login/', accounts.other)).status).toBe(200)
  expect((await execute(page, 'Submissions-submissions_detail', `/submissions/detail/${id}/`, undefined, { id })).status).toBe(404)
  expect((await execute(page, 'Authentication-auth_logout', '/auth/logout/')).status).toBe(200)
  expect((await execute(page, 'Authentication-auth_login', '/auth/login/', accounts.reviewer)).status).toBe(200)
  const invalid = await execute(page, 'Submissions-submissions_decision', `/submissions/decision/${id}/`, { decision: 'rejected', note: '' }, { id })
  expect(invalid.status).toBe(400)
  expect(invalid.body.errors.note).toBeDefined()
  const decided = await execute(page, 'Submissions-submissions_decision', `/submissions/decision/${id}/`, { decision: 'approved', note: 'Swagger verification passed.' }, { id })
  expect(decided.status).toBe(200)
  expect(decided.body.data.status).toBe('approved')
  const history = await execute(page, 'Submissions-submissions_history', `/submissions/history/${id}/`, undefined, { id })
  expect(history.status).toBe(200)
  expect(history.body.data.map((event: { event_type: string }) => event.event_type)).toEqual(['submitted', 'approved'])
  expect((await execute(page, 'Authentication-auth_logout', '/auth/logout/')).status).toBe(200)
})
