// Read all public Arad vehicle positions once. Standard library only.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

const (
	liveBase = "https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport"
	dataBase = "https://baditaflorin.github.io/arad-transport-open-data/data"
)

type Route struct {
	ID        int    `json:"id"`
	ShortName string `json:"shortName"`
	LongName  string `json:"longName"`
	Mode      string `json:"mode"` // tram or bus, added by the static export
}

type Stop struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

type Vehicle struct {
	VehicleID       string    `json:"vehicleId"`
	Label           string    `json:"label"`
	RouteID         int       `json:"routeId"`
	PatternIndex    int       `json:"patternIndex"`
	TripID          string    `json:"tripId"`
	Latitude        float64   `json:"latitude"`
	Longitude       float64   `json:"longitude"`
	Heading         float64   `json:"heading"`
	Speed           *float64  `json:"speed"` // Optional. Unit not documented here.
	DelaySeconds    int       `json:"delaySeconds"`
	StopID          int       `json:"stopId"`
	StopStatus      string    `json:"stopStatus"`
	LastUpdated     time.Time `json:"lastUpdated"`
	NextStopArrival time.Time `json:"nextStopArrival"`
}

func getJSON[T any](ctx context.Context, client *http.Client, url string) (T, error) {
	var result T
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return result, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "AradTransportHackathonExample/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return result, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return result, fmt.Errorf("GET %s: HTTP %d", url, resp.StatusCode)
	}
	// Bound memory if an upstream response is unexpectedly large.
	err = json.NewDecoder(io.LimitReader(resp.Body, 5<<20)).Decode(&result)
	return result, err
}

func run(ctx context.Context) error {
	client := &http.Client{Timeout: 20 * time.Second}
	routes, err := getJSON[[]Route](ctx, client, dataBase+"/routes.json")
	if err != nil {
		return err
	}
	stops, err := getJSON[[]Stop](ctx, client, dataBase+"/stops.json")
	if err != nil {
		return err
	}
	vehicles, err := getJSON[[]Vehicle](ctx, client, liveBase+"/planner/vehicles")
	if err != nil {
		return err
	}
	routesByID := make(map[int]Route, len(routes))
	for _, route := range routes {
		routesByID[route.ID] = route
	}
	stopsByID := make(map[int]Stop, len(stops))
	for _, stop := range stops {
		stopsByID[stop.ID] = stop
	}
	now := time.Now()
	for _, vehicle := range vehicles {
		route, known := routesByID[vehicle.RouteID]
		if !known {
			route.ShortName = fmt.Sprintf("unknown routeId=%d", vehicle.RouteID)
		}
		age := now.Sub(vehicle.LastUpdated)
		freshness := "recent"
		if vehicle.LastUpdated.IsZero() || age > 120*time.Second {
			freshness = "STALE"
		}
		fmt.Printf("line=%s mode=%s vehicle=%s lat=%.6f lon=%.6f nextStop=%q delay=%ds updated=%s [%s]\n",
			route.ShortName, route.Mode, vehicle.VehicleID, vehicle.Latitude, vehicle.Longitude,
			stopsByID[vehicle.StopID].Name, vehicle.DelaySeconds, vehicle.LastUpdated.Format(time.RFC3339), freshness)
	}
	return nil
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	if err := run(ctx); err != nil {
		log.Fatal(err)
	}
}
