import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

interface Fixture {
  email: string
  password: string
  tenant_id: string
  tenant_name: string
  site_id: string
  site_name: string
  asset_id: string
  asset_name: string
  device_id: string
}

function fixture(): Fixture {
  const path = process.env.GUARDIAN_V08_FIXTURE
  if (!path) throw new Error('GUARDIAN_V08_FIXTURE is required')
  return JSON.parse(readFileSync(path, 'utf-8')) as Fixture
}

test('certifies secure scoped endpoint workflow through the real Web Console', async ({ page, context }) => {
  const data = fixture()
  const initial = await page.goto('login')
  expect(initial?.status()).toBe(200)
  const headers = initial?.headers() ?? {}
  expect(headers['content-security-policy']).toContain("default-src 'self'")
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['cache-control']).toContain('no-store')

  await page.getByLabel('Correo electrónico').fill(data.email)
  await page.getByLabel('Contraseña').fill(data.password)
  await page.getByRole('button', { name: 'Iniciar sesión' }).click()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

  const cookies = await context.cookies()
  const sessionCookie = cookies.find((cookie) => cookie.name === 'itg_session')
  expect(sessionCookie).toBeTruthy()
  expect(sessionCookie?.httpOnly).toBe(true)
  expect(sessionCookie?.sameSite).toBe('Strict')

  const storage = await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }))
  expect(storage.local).toEqual([])
  expect(storage.session).toEqual([])

  const tenantSelect = page.getByLabel('Seleccionar empresa')
  await expect(tenantSelect).toHaveValue(data.tenant_id)
  await expect(tenantSelect.locator(`option[value="${data.tenant_id}"]`)).toHaveText(data.tenant_name)
  const siteSelect = page.getByLabel('Seleccionar sede')
  await expect(siteSelect.locator(`option[value="${data.site_id}"]`)).toHaveText(data.site_name)
  await siteSelect.selectOption(data.site_id)
  await expect(siteSelect).toHaveValue(data.site_id)

  await page.getByRole('link', { name: 'Dispositivos' }).click()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.getByText('ONLINE')).toBeVisible()
  await page.locator('a.primary-link').first().click()
  await expect(page.getByRole('heading', { name: 'Windows endpoint' })).toBeVisible()
  await expect(page.getByText('17.5%')).toBeVisible()
  await expect(page.getByText(/3 GB \/ 8 GB|3\.0 GB \/ 8\.0 GB/i)).toBeVisible()

  await page.getByRole('button', { name: 'Ejecutar comando' }).click()
  await expect(page.getByText(/Comando creado:/)).toBeVisible()
  await expect(page.getByText('SUCCEEDED')).toBeVisible({ timeout: 70_000 })

  await page.getByRole('link', { name: 'Auditoría' }).click()
  await expect(page.getByText(/Integridad de cadena/)).toBeVisible()
  await expect.poll(async () => {
    const body = await page.locator('body').innerText()
    if (body.includes('command.succeeded')) return body
    await page.reload()
    await page.waitForLoadState('networkidle')
    return page.locator('body').innerText()
  }, { timeout: 70_000, intervals: [1000, 2000, 3000] }).toContain('command.succeeded')

  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await expect(page.getByRole('button', { name: 'Iniciar sesión' })).toBeVisible()
  expect((await context.cookies()).some((cookie) => cookie.name === 'itg_session')).toBe(false)
})
