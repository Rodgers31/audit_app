'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const { test } = require('node:test');
const redirects = require('follow-redirects');

async function crossOriginHeaders(t, headers, sensitiveHeaders) {
  let initialHeaders;
  let redirectedHeaders;
  const target = http.createServer((request, response) => {
    redirectedHeaders = request.headers;
    response.end('ok');
  });
  const origin = http.createServer((request, response) => {
    initialHeaders = request.headers;
    response.writeHead(302, {
      location: `http://localhost:${target.address().port}/target`,
    });
    response.end();
  });
  t.after(() => {
    origin.closeAllConnections();
    target.closeAllConnections();
    origin.close();
    target.close();
  });
  target.listen(0, '127.0.0.1');
  await once(target, 'listening');
  origin.listen(0, '127.0.0.1');
  await once(origin, 'listening');

  await new Promise((resolve, reject) => {
    const request = redirects.http.get({
      hostname: '127.0.0.1',
      port: origin.address().port,
      path: '/origin',
      headers,
      sensitiveHeaders,
      maxRedirects: 1,
      timeout: 1000,
      // Both hostnames resolve only to our IPv4 loopback fixtures.
      lookup(_hostname, options, callback) {
        callback(null, options.all ? [{ address: '127.0.0.1', family: 4 }] : '127.0.0.1', 4);
      },
    }, response => {
      assert.equal(response.statusCode, 200);
      response.resume();
      response.on('end', resolve);
      response.on('error', reject);
    });
    request.on('error', reject);
    request.on('timeout', () => request.destroy(new Error('loopback redirect timed out')));
  });
  assert.ok(initialHeaders, 'the origin must receive a request');
  assert.ok(redirectedHeaders, 'the redirect target must receive a request');
  assert.equal(redirectedHeaders['x-public'], 'visible');
  return { initialHeaders, redirectedHeaders };
}

test('array-form headers lose credentials on a cross-origin redirect', { timeout: 4000 }, async t => {
  const { initialHeaders, redirectedHeaders } = await crossOriginHeaders(t, [
    'Host', '127.0.0.1',
    'Authorization', 'Bearer inert-fixture',
    'Cookie', 'session=inert-fixture',
    'Proxy-Authorization', 'Basic inert-fixture',
    'X-Public', 'visible',
  ]);
  const expected = {
    authorization: 'Bearer inert-fixture',
    cookie: 'session=inert-fixture',
    'proxy-authorization': 'Basic inert-fixture',
  };
  for (const [header, value] of Object.entries(expected)) {
    assert.equal(initialHeaders[header], value, `the origin must receive the original ${header}`);
    assert.equal(redirectedHeaders[header], undefined, `${header} crossed origins`);
  }
});

test('custom credential header names are matched literally', { timeout: 4000 }, async t => {
  const name = 'x-fixture^credential';
  const { initialHeaders, redirectedHeaders } = await crossOriginHeaders(t, {
    [name]: 'inert-fixture',
    'x-public': 'visible',
  }, [name]);
  assert.equal(initialHeaders[name], 'inert-fixture');
  assert.equal(redirectedHeaders[name], undefined);
});
