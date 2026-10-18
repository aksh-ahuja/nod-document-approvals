import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function signIn(page: Page, email: string) {
  await page.goto('/#/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill('NodDemo!2026')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: /My submissions|Assigned to me/ })).toBeVisible()
}

async function signOut(page: Page) {
  const menu = page.getByRole('button', { name: 'Open navigation' })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
}

test('submit, enforce assignment, reject with feedback, and track the decision', async ({
  page,
}) => {
  const name = `review-request-${Date.now()}`
  const title = `PAN card · ${name}`
  await signIn(page, 'jamie@nod.demo')
  await page.goto('/#/new')
  await page.getByRole('button', { name: /PAN card/ }).click()
  await page.getByLabel('Upload document').setInputFiles({
    name: `${name}.txt`,
    mimeType: 'text/plain',
    buffer: Buffer.from('Please review the campaign budget and launch date.'),
  })
  await page
    .getByRole('combobox', { name: 'Send to', exact: true })
    .selectOption({ label: 'Alex Rivera · alex@nod.demo' })
  await page.getByRole('button', { name: 'Send for review' }).click()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  const detailUrl = page.url()
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
  await signOut(page)
  await signIn(page, 'sam@nod.demo')
  await page.goto(detailUrl)
  await expect(page.getByRole('alert')).toContainText('not available')
  await signOut(page)
  await signIn(page, 'alex@nod.demo')
  await page.goto(detailUrl)
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Confirm rejection' })).toBeDisabled()
  await page.getByLabel('What needs to change?').fill('Please add an itemised budget.')
  await page.getByRole('button', { name: 'Confirm rejection' }).click()
  await expect(page.getByRole('heading', { name: 'Rejected', exact: true })).toBeVisible()
  await expect(page.getByText('Please add an itemised budget.', { exact: true })).toBeVisible()
  await signOut(page)
  await signIn(page, 'jamie@nod.demo')
  await page.goto(detailUrl)
  await expect(page.getByRole('heading', { name: 'Rejected', exact: true })).toBeVisible()
  await expect(page.getByText('Please add an itemised budget.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
})

test('landing and registration are accessible without an account', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Give good work.*the green light/ })).toBeVisible()
  await page.getByRole('link', { name: 'Get started' }).click()
  await expect(page.getByLabel('Full name')).toBeVisible()
  await expect(page.getByLabel('Email address')).toBeVisible()
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
})

test('filter, search, and clear the document list', async ({ page }) => {
  await signIn(page, 'alex@nod.demo')
  await page.goto('/#/review')
  const filters = page.getByRole('group', { name: 'Filter by status' })
  await filters.getByRole('button', { name: /Pending/ }).click()
  await expect(page.locator('tbody .status').first()).toBeVisible()
  for (const status of await page.locator('tbody .status').all()) {
    await expect(status).toHaveText('Pending')
  }
  await page.getByLabel('Search submissions').fill(`no-matching-document-${Date.now()}`)
  await expect(page.getByRole('heading', { name: 'No matching documents' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()
  await expect(page.locator('tbody .status').first()).toBeVisible()
  await filters.getByRole('button', { name: /All documents/ }).click()
  await expect(filters.getByRole('button', { name: /All documents/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  const menu = page.getByRole('button', { name: 'Open navigation' })
  if (await menu.isVisible()) {
    await menu.click()
    await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toBeFocused()
    await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeHidden()
  }
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
})

test('upload a document, view its private preview, and approve it', async ({ page }) => {
  const name = `proposal-${Date.now()}`
  const title = `Aadhaar card · ${name}`
  await signIn(page, 'jamie@nod.demo')
  await page.goto('/#/new')
  await page.getByRole('button', { name: /Aadhaar card/ }).click()
  await page.getByLabel('Upload document').setInputFiles({
    name: `${name}.txt`,
    mimeType: 'text/plain',
    buffer: Buffer.from('Launch budget: 25000. Please approve.'),
  })
  await page
    .getByRole('combobox', { name: 'Send to', exact: true })
    .selectOption({ label: 'Alex Rivera · alex@nod.demo' })
  const createRequest = page.waitForRequest((request) =>
    request.url().includes('/api/v1/submissions/create/') && request.method() === 'POST',
  )
  const transferRequest = page.waitForRequest((request) =>
    request.url().includes('/api/v1/uploads/content/') && request.method() === 'PUT',
  )
  await page.getByRole('button', { name: 'Send for review' }).click()
  const transfer = await transferRequest
  // Chromium can omit file-backed bodies from request inspection; verify persisted bytes below.
  expect((await transfer.response())?.status()).toBe(201)
  expect(transfer.headers()['content-type']).toBe('text/plain')
  const creation = await createRequest
  expect(creation.headers()['content-type']).toContain('application/json')
  expect(creation.postDataJSON().upload_id).toBeTruthy()
  expect(creation.postDataJSON().file).toBeUndefined()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  const detailUrl = page.url()
  await signOut(page)
  await signIn(page, 'alex@nod.demo')
  await page.goto(detailUrl)
  await page.getByRole('button', { name: 'View document', exact: true }).click()
  await expect(page.frameLocator('iframe').locator('body')).toContainText('Launch budget: 25000. Please approve.')
  await expect(page.getByRole('link', { name: 'Open in new tab' })).toHaveAttribute(
    'href',
    /token=/,
  )
  await expect(page.getByRole('button', { name: 'Download original' })).toBeEnabled()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Approved', exact: true })).toBeVisible()
})
