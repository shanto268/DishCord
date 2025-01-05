import os
import subprocess


def export_environment(output_dir="env_files"):
    """
    Generates files to replicate the current Python environment:
    - `requirements.txt` for pip-installed packages
    - `environment.yml` for Conda-based environments
    
    Parameters:
        output_dir (str): Directory to store the generated files.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Export pip-installed packages
    requirements_path = os.path.join(output_dir, "requirements.txt")
    try:
        with open(requirements_path, "w") as f:
            subprocess.run(["pip", "freeze"], stdout=f, check=True)
        print(f"Generated {requirements_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error generating requirements.txt: {e}")

    # Export Conda environment
    environment_yml_path = os.path.join(output_dir, "environment.yml")
    try:
        with open(environment_yml_path, "w") as f:
            subprocess.run(["conda", "env", "export"], stdout=f, check=True)
        print(f"Generated {environment_yml_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error generating environment.yml: {e}")


if __name__ == "__main__":
    export_environment()
