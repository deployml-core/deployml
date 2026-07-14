# Contributing to deployml

We welcome contributors who are interested in helping with issues/bugs and expanding and improving upon what has already been built. Please note that since this is an academic project that is supervised by one faculty member, and maintained by students, it is not always possible to respond promptly to messages.

## Ways to Contribute

You can help improve the project in several ways:

- Bug reports: Identify issues with deployment, configuration, or documentation ([open an issue](https://github.com/deployml-core/deployml/issues)).  
- Feature requests: Suggest improvements that would benefit classroom use or learning ([open an issue](https://github.com/deployml-core/deployml/issues)).  
- Code contributions: Add features, fix bugs, or improve reliability (submit a pull request).  
- Documentation: Improve setup guides, examples, or explanations for students and instructors (submit a pull request).  
- Educational feedback: Share insights about how the tool works in a teaching or learning context (contact info [here](https://robertclements.org/)).

## Getting Started with Code or Documentation Contributions

1. Fork the repository and clone your fork locally.  
2. Follow the setup instructions in the main README to install dependencies and configure your environment.  
3. Create a new branch for your work with a descriptive name (e.g., fix-deployment-logging or add-example-yaml).

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management, building, and publishing.

- Install dependencies (including the `dev` group): `uv sync`
- Run the tests: `uv run pytest`
- Build the package locally: `uv build`

## Releases and Commit Messages

Releases are fully automated with [python-semantic-release](https://python-semantic-release.readthedocs.io/). The next version, changelog, git tag, GitHub Release, and PyPI upload are all derived from commit messages on `main`, so **do not bump the version by hand**.

Use [Conventional Commits](https://www.conventionalcommits.org/) so the version bump is correct:

- `fix:` → patch release (e.g. `0.1.0` → `0.1.1`)
- `feat:` → minor release (e.g. `0.1.0` → `0.2.0`)
- `feat!:` or a `BREAKING CHANGE:` footer → major release
- `docs:`, `chore:`, `refactor:`, `test:`, etc. → no release on their own

## Submitting a Pull Request

1. Push your changes to your fork.  
2. Open a pull request against the main branch.  
3. In the pull request description, briefly explain:  
    - What the change does. 
    - Why it is needed. 
    - How it was tested.

Pull requests may be reviewed with an emphasis on clarity, maintainability, and suitability for classroom use.

## Reporting Issues

If you find a bug or have a suggestion, please [open an issue](https://github.com/deployml-core/deployml/issues) and include:

- A clear description of the problem or idea. 
- Steps to reproduce (if applicable). 
- Relevant logs, error messages, or screenshots.

## Code of Conduct

All contributors are expected to engage respectfully and constructively. This project follows a standard open-source code of conduct: be inclusive, be professional, and assume good intent.