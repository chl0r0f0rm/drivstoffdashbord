/**
 * Static asset passthrough. Auth er midlertidig pauset.
 * Auth-kode ligger i worker.auth.js når den skal slås på igjen.
 */
export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
