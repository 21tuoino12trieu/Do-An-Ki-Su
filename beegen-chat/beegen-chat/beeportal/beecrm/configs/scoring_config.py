from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT


class ScoringConfig(YamlModel):
    domain: str
    
    @classmethod
    def default(cls) -> 'ScoringConfig':
        """Load default config"""
        dict = ScoringConfig.read_yaml(BEEGEN_ROOT / "config/crm.yaml")
        return ScoringConfig(**dict)
    
if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    config = ScoringConfig.default()
    print(config)