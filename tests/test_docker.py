import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DockerDeploymentTests(unittest.TestCase):
    def test_flattened_source_layout_and_image_paths_match(self):
        self.assertTrue((ROOT / "music/AoiMusic").is_dir())
        self.assertTrue((ROOT / "waifu/aoiwaifu").is_dir())
        self.assertFalse((ROOT / "components").exists())
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=/app/music:/app/waifu", dockerfile)
        self.assertIn("WORKDIR /app/music", dockerfile)
        self.assertIn('CMD ["python", "/app/launcher.py"]', dockerfile)
        self.assertIn("USER fiona", dockerfile)
        self.assertIn("ffmpeg", dockerfile)

    def test_example_configuration_has_no_fake_external_service_url(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("MEDIA_API_URL=\n", env_example)
        self.assertNotIn("host-repository.vercel.app", env_example)
        self.assertNotIn("t.me/your_", env_example)

    def test_compose_runs_one_service_with_runtime_env_file(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("  fiona:", compose)
        self.assertIn("dockerfile: Dockerfile", compose)
        self.assertIn("- .env", compose)
        self.assertEqual(compose.count("\n  fiona:"), 1)

    def test_secrets_are_excluded_from_docker_build_context(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env", dockerignore)
        self.assertIn("*.session", dockerignore)
        self.assertIn(".venv-*", dockerignore)


if __name__ == "__main__":
    unittest.main()
