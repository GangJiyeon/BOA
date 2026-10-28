from app.models.moisture import MoistureObservation
from app.schemas.moisture import CompletedReceipt


def observation_receipt(row: MoistureObservation) -> CompletedReceipt:
    return CompletedReceipt(measurement_id=row.measurement_id, analysis_id=row.analysis_id,
                            site=row.payload['site'], measured_at=row.payload['measured_at'],
                            baseline=row.payload['baseline'], algorithm_version=row.payload['algorithm_version'],
                            **row.summary)


