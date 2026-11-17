'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const retryMacRunner = require('../scripts/retry-macos-runner.cjs');

test('Mac workflow keeps the job names used by recovery when matrix fields change', () => {
  const workflow = readFileSync(join(__dirname, '../workflows/macos-vision.yml'), 'utf8');
  assert.match(workflow, /^    name: native-mac \(\$\{\{ matrix\.os \}\}\)$/m);
});

function fixture() {
  const run = {
    name: 'macOS Vision Studio', path: '.github/workflows/macos-vision.yml',
    head_repository: { full_name: 'msnouri/PokerLab' }, head_branch: 'main',
    event: 'push', status: 'completed', conclusion: 'failure',
    run_attempt: 1, head_sha: 'current',
  };
  const jobs = [
    { id: 100, name: 'native-mac (macos-15)', status: 'completed',
      conclusion: 'cancelled', runner_id: 0, steps: [] },
    { id: 101, name: 'native-mac (macos-15-intel)', status: 'completed',
      conclusion: 'success', runner_id: 42, steps: [{ name: 'Tests' }] },
  ];
  const requests = [];
  const messages = [];
  const head = { commit: { sha: 'current' } };
  const context = { repo: { owner: 'msnouri', repo: 'PokerLab' }, payload: {
    workflow_run: { id: 99 }, repository: { default_branch: 'main' },
  } };
  const core = { info: (message) => messages.push(message), summary: {
    addHeading() { return this; }, addRaw() { return this; }, async write() {},
  } };
  const github = {
    rest: {
      actions: {
        getWorkflowRun: async () => ({ data: run }),
        listJobsForWorkflowRun: () => {},
      },
      repos: { getBranch: async () => ({ data: head }) },
    },
    paginate: async (_method, params) => {
      assert.equal(params.filter, 'latest');
      assert.equal(params.run_id, 99);
      return jobs;
    },
    request: async (route, params) => requests.push({ route, params }),
  };
  return { run, jobs, requests, messages, head,
    execute: () => retryMacRunner({ github, context, core }) };
}

test('retries only the unassigned cancelled job, leaving passing Intel alone', async () => {
  const f = fixture();
  await f.execute();
  assert.deepEqual(f.requests, [{
    route: 'POST /repos/{owner}/{repo}/actions/jobs/{job_id}/rerun',
    params: { owner: 'msnouri', repo: 'PokerLab', job_id: 100 },
  }]);
  assert.match(f.messages[0], /attempt 2\/3/);
});

for (const [name, mutate] of [
  ['test failure', f => { f.jobs[0].conclusion = 'failure'; }],
  ['cancelled after setup', f => { f.jobs[0].steps = [{ name: 'Set up job' }]; }],
  ['assigned runner', f => { f.jobs[0].runner_id = 42; }],
  ['missing runner evidence', f => { delete f.jobs[0].runner_id; }],
  ['missing step evidence', f => { delete f.jobs[0].steps; }],
  ['unrelated job', f => { f.jobs[0].name = 'evidence'; }],
  ['active run', f => { f.run.status = 'in_progress'; }],
  ['successful run', f => { f.run.conclusion = 'success'; }],
  ['operator cancellation', f => { f.run.conclusion = 'cancelled'; }],
  ['third attempt', f => { f.run.run_attempt = 3; }],
  ['later attempt', f => { f.run.run_attempt = 4; }],
  ['missing attempt evidence', f => { delete f.run.run_attempt; }],
  ['superseded commit', f => { f.head.commit.sha = 'newer'; }],
  ['fork', f => { f.run.head_repository.full_name = 'someone/PokerLab'; }],
  ['pull request', f => { f.run.event = 'pull_request'; }],
  ['feature branch', f => { f.run.head_branch = 'feature'; }],
  ['wrong workflow name', f => { f.run.name = 'Other checks'; }],
  ['wrong workflow path', f => { f.run.path = '.github/workflows/other.yml'; }],
]) {
  test(`does not retry ${name}`, async () => {
    const f = fixture();
    mutate(f);
    await f.execute();
    assert.deepEqual(f.requests, []);
    assert.equal(f.messages.length, 1);
  });
}

test('second attempt can request the final allowed retry', async () => {
  const f = fixture();
  f.run.run_attempt = 2;
  await f.execute();
  assert.equal(f.requests.length, 1);
  assert.match(f.messages[0], /attempt 3\/3/);
});

test('requests at most one job per completion', async () => {
  const f = fixture();
  f.jobs[1] = { ...f.jobs[0], id: 101, name: 'native-mac (macos-15-intel)' };
  await f.execute();
  assert.equal(f.requests.length, 1);
});
