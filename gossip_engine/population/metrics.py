from __future__ import annotations


def archive_occupancy(archive) -> float:
    return archive.occupancy()


def population_size(population) -> int:
    return population.size


def failure_rate(population) -> float:
    return population.failure_rate()
