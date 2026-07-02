/**
 * @reos/config public API — WP-002-02.
 *
 * Usage: `import { getConfig } from "@reos/config";`
 */

export {
  ENVIRONMENTS,
  getConfig,
  resetConfigForTesting,
} from "./config";
export type { Environment, EnvSource, ReosConfig } from "./config";
