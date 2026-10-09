-- CreateEnum
CREATE TYPE "EvidenceSource" AS ENUM ('OPENWEB_NINJA', 'CITIZEN', 'RESPONDER', 'GOVERNMENT', 'WEATHER', 'SATELLITE');

-- CreateEnum
CREATE TYPE "ConditionType" AS ENUM ('ROAD_CLOSED', 'ROAD_BLOCKED', 'FLOODED', 'ACCIDENT', 'TRAFFIC', 'OTHER');

-- CreateEnum
CREATE TYPE "RoadStatus" AS ENUM ('OPEN', 'RISKY', 'BLOCKED', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "ConfidenceLevel" AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'UNKNOWN');

-- CreateTable
CREATE TABLE "RoadConditionEvidence" (
    "id" TEXT NOT NULL,
    "source" "EvidenceSource" NOT NULL,
    "externalId" TEXT,
    "conditionType" "ConditionType" NOT NULL,
    "status" "RoadStatus" NOT NULL,
    "latitude" DOUBLE PRECISION NOT NULL,
    "longitude" DOUBLE PRECISION NOT NULL,
    "street" TEXT,
    "severity" INTEGER,
    "confidence" "ConfidenceLevel" NOT NULL DEFAULT 'UNKNOWN',
    "reportedAt" TIMESTAMP(3) NOT NULL,
    "expiresAt" TIMESTAMP(3),
    "rawMetadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "RoadConditionEvidence_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "RoadConditionEvidence_latitude_longitude_idx" ON "RoadConditionEvidence"("latitude", "longitude");

-- CreateIndex
CREATE INDEX "RoadConditionEvidence_source_externalId_idx" ON "RoadConditionEvidence"("source", "externalId");

-- CreateIndex
CREATE INDEX "RoadConditionEvidence_status_idx" ON "RoadConditionEvidence"("status");

-- CreateIndex
CREATE INDEX "RoadConditionEvidence_reportedAt_idx" ON "RoadConditionEvidence"("reportedAt");
