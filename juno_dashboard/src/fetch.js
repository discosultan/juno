export async function fetchJson(method, url, body, signal) {
  const response = await fetch(url, {
    method,
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify(body, camelToSnakeReplacer),
    signal,
  });
  const text = await response.text();
  return JSON.parse(text, snakeToCamelReviver);
}

function camelToSnakeReplacer(_key, value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const replacement = {};
    for (const [objKey, objValue] of Object.entries(value)) {
      replacement[objKey.replace(/([A-Z])/g, '_$1').toLowerCase()] = objValue;
    }
    return replacement;
  }
  return value;
}

function snakeToCamelReviver(_key, value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const replacement = {};
    for (const [objKey, objValue] of Object.entries(value)) {
      replacement[objKey.replace(/(_\w)/g, (k) => k[1].toUpperCase())] = objValue;
    }
    return replacement;
  }
  return value;
}
