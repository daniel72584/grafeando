package main

import "fmt"

type Service struct {
	Name string
}

func (s *Service) ExecuteQuery(query string) string {
	return fmt.Sprintf("Result for %s", query)
}

type Controller struct {
	svc *Service
}

func (c *Controller) HandleRequest() {
	res := c.svc.ExecuteQuery("SELECT 1")
	fmt.Println(res)
}

func main() {
	svc := &Service{Name: "MainService"}
	ctrl := &Controller{svc: svc}
	ctrl.HandleRequest()
}
