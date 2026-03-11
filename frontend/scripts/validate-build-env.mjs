const apiBaseUrl = (process.env.VITE_API_BASE_URL || '').trim();
const strictBuild = process.env.CI === 'true' || process.env.VITE_STRICT_API_BASE_URL === 'true';

if (!strictBuild) {
  process.exit(0);
}

if (!apiBaseUrl) {
  console.error('VITE_API_BASE_URL is required for CI/production builds.');
  process.exit(1);
}

if (apiBaseUrl.startsWith('/')) {
  console.error(`VITE_API_BASE_URL must be an absolute URL for CI/production builds; got: ${apiBaseUrl}`);
  process.exit(1);
}

let parsed;
try {
  parsed = new URL(apiBaseUrl);
} catch {
  console.error(`VITE_API_BASE_URL must be a valid absolute URL; got: ${apiBaseUrl}`);
  process.exit(1);
}

if (!['https:', 'http:'].includes(parsed.protocol)) {
  console.error(`VITE_API_BASE_URL must use http or https; got: ${apiBaseUrl}`);
  process.exit(1);
}
