export default function () {
  return {
    repo: process.env.DOCS_REPO || process.env.GITHUB_REPOSITORY || "",
  };
};
