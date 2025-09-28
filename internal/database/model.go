package database

import (
	"time"
)

type Flavor struct {
	Platform        string   `db:"platform"         json:"platform"`
	Name            string   `db:"name"             json:"name"`
	Labels          []string `db:"labels"           json:"labels"`
	Priority        int      `db:"priority"         json:"priority"`
	IsDisabled      bool     `db:"is_disabled"      json:"is_disabled"`
	MinimumPressure int      `db:"minimum_pressure" json:"minimum_pressure"`
}

type Job struct {
	Platform       string                 `db:"platform"        json:"platform"`
	ID             string                 `db:"id"              json:"id"`
	Labels         []string               `db:"labels"          json:"labels"`
	CreatedAt      time.Time              `db:"created_at"      json:"created_at"`
	StartedAt      *time.Time             `db:"started_at"      json:"started_at,omitempty"`
	CompletedAt    *time.Time             `db:"completed_at"    json:"completed_at,omitempty"`
	Raw            map[string]interface{} `db:"raw"             json:"raw"`
	AssignedFlavor *string                `db:"assigned_flavor" json:"assigned_flavor,omitempty"`
}
